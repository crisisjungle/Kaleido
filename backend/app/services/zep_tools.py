from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SearchResult:
    query: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)

    def to_text(self) -> str:
        if not self.results:
            return f"未检索到与“{self.query}”直接相关的图谱结果。"
        lines = []
        for item in self.results:
            name = item.get("name") or item.get("title") or item.get("source_agent_name") or "结果"
            summary = item.get("summary") or item.get("content") or item.get("rationale") or ""
            lines.append(f"- {name}: {summary}")
        return "\n".join(lines)


@dataclass
class InsightForgeResult(SearchResult):
    pass


@dataclass
class PanoramaResult(SearchResult):
    pass


@dataclass
class AgentStateSummaryResult(SearchResult):
    """Deterministic state cards for selected agents.

    This is NOT an interview and NOT a first-person quote. Each entry is a
    summary of the agent's *observed* metrics (state_vector) at the latest
    snapshot. We deliberately frame the text as observed numbers so it cannot
    be mistaken for qualitative testimony the agent "said".
    """

    def to_text(self) -> str:
        if not self.results:
            return f"未找到与“{self.query}”相关的 Agent 状态卡（无可读取的状态向量）。"
        lines = [
            "Agent 状态卡（观测指标，非采访/非原话；以下为状态向量的确定性摘要）：",
        ]
        for item in self.results:
            name = item.get("name") or "结果"
            summary = item.get("summary") or ""
            lines.append(f"- {name}: {summary}")
        return "\n".join(lines)


@dataclass
class InterviewResult(AgentStateSummaryResult):
    """Backward-compatible alias retained for callers that still import it.

    Inherits the honest state-card framing; it is no longer a fake interview.
    """
    pass


@dataclass
class EntityNode:
    uuid: str
    name: str
    labels: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"uuid": self.uuid, "name": self.name, "labels": self.labels, "summary": self.summary}


class ZepToolsService:
    """Report-facing tools backed by local EnvFish artifacts.

    The original Zep-backed interface is kept, but this app's current report
    path needs a reliable local fallback so reports are grounded in the
    simulation files even when graph memory is absent or still rebuilding.
    """

    def __init__(self):
        self._bundle_cache: Dict[str, Dict[str, Any]] = {}
        self._graph_to_simulation: Dict[str, str] = {}

    def insight_forge(self, graph_id: str, query: str, simulation_requirement: str = "", report_context: str = "") -> InsightForgeResult:
        simulation_id = self._simulation_id_from_context(report_context) or self._graph_to_simulation.get(graph_id, "")
        results: List[Dict[str, Any]] = []
        if simulation_id:
            results.extend(self._fact_results(simulation_id, limit=8))
        if simulation_requirement or report_context:
            results.insert(
                0,
                {
                    "name": "场景上下文",
                    "summary": simulation_requirement or report_context,
                },
            )
        return InsightForgeResult(query=query, results=results)

    def panorama_search(self, graph_id: str, query: str, include_expired: bool = True) -> PanoramaResult:
        simulation_id = self._graph_to_simulation.get(graph_id, "")
        return PanoramaResult(query=query, results=self._fact_results(simulation_id, limit=10) if simulation_id else [])

    def quick_search(self, graph_id: str, query: str, limit: int = 10) -> SearchResult:
        simulation_id = self._graph_to_simulation.get(graph_id, "")
        return SearchResult(query=query, results=self._fact_results(simulation_id, limit=limit) if simulation_id else [])

    def summarize_agent_state(self, simulation_id: str, focus: str = "", simulation_requirement: str = "", max_agents: int = 5) -> AgentStateSummaryResult:
        """Return deterministic *state cards* (observed metrics) for top agents.

        This replaces the former ``interview_agents`` pseudo-interview. It does
        NOT fabricate first-person quotes or "原话"; every entry reports the
        agent's observed state_vector numbers and recorded action types, framed
        as observed metrics so the report cannot dress them up as testimony.
        """
        bundle = self._load_bundle(simulation_id)
        latest = self._latest_snapshot(bundle)
        interactions = (bundle.get("artifacts") or {}).get("agent_interactions") or []
        top_agents = latest.get("top_agents") or latest.get("top_active_agents") or latest.get("agents") or []
        results = []
        for item in top_agents[:max_agents]:
            name = item.get("agent_name") or item.get("name") or f"Agent {item.get('agent_id', '')}"
            region = item.get("primary_region") or item.get("region_name") or ""
            vector = item.get("state_vector") or {}
            results.append(
                {
                    "name": name,
                    "summary": (
                        f"位置 {region or '未标注区域'}；"
                        f"观测状态向量——脆弱性 {self._num(vector.get('vulnerability_score'))}，"
                        f"恐慌指数 {self._num(vector.get('panic_level'))}，"
                        f"响应能力 {self._num(vector.get('response_capacity'))}"
                        f"（数值仅供排序，未经标定，不可作为概率或效应量）。"
                    ),
                }
            )
        for item in interactions[: max(0, max_agents - len(results))]:
            action = item.get("action_type") or ""
            rationale = item.get("rationale") or ""
            note = "，".join(part for part in (action, rationale) if part) or "无记录动作"
            results.append(
                {
                    "name": item.get("source_agent_name") or "交互样本",
                    "summary": f"记录到的动作（observed action，非原话）：{note}。",
                }
            )
        return AgentStateSummaryResult(query=focus, results=results)

    def interview_agents(self, simulation_id: str, interview_requirement: str = "", simulation_requirement: str = "", max_agents: int = 5) -> InterviewResult:
        """Deprecated alias. Delegates to :meth:`summarize_agent_state`.

        Retained only for backward compatibility with external callers. It no
        longer produces an interview/quote — it returns the same honest state
        cards. Prefer ``summarize_agent_state`` in new code.
        """
        summary = self.summarize_agent_state(
            simulation_id=simulation_id,
            focus=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents,
        )
        return InterviewResult(query=summary.query, results=summary.results)

    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        simulation_id = self._graph_to_simulation.get(graph_id, "")
        if simulation_id:
            context = self.get_simulation_context(simulation_id=simulation_id, graph_id=graph_id)
            return context.get("graph_statistics") or {}
        return {"graph_id": graph_id, "node_count": 0, "edge_count": 0}

    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        return {"graph_id": graph_id, "entity_name": entity_name, "summary": ""}

    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[EntityNode]:
        return []

    def get_simulation_context(self, simulation_id: str = "", **kwargs) -> Dict[str, Any]:
        simulation_id = kwargs.get("simulation_id") or simulation_id
        graph_id = kwargs.get("graph_id") or ""
        simulation_requirement = kwargs.get("simulation_requirement") or ""
        bundle = self._load_bundle(simulation_id)
        state = bundle.get("state") or {}
        config = bundle.get("config") or {}
        artifacts = bundle.get("artifacts") or {}
        latest = self._latest_snapshot(bundle)

        if not graph_id:
            graph_id = state.get("graph_id") or config.get("graph_id") or ""
        if graph_id and simulation_id:
            self._graph_to_simulation[graph_id] = simulation_id
        if not simulation_requirement:
            simulation_requirement = config.get("simulation_requirement") or state.get("simulation_requirement") or ""

        agents = config.get("agent_configs") or config.get("actor_profiles") or latest.get("agents") or []
        regions = artifacts.get("region_graph") or config.get("region_graph") or latest.get("regions") or []
        subregions = artifacts.get("subregion_graph") or config.get("subregion_graph") or latest.get("subregions") or []
        risk_objects = artifacts.get("risk_objects") or config.get("risk_objects") or []
        interactions = artifacts.get("agent_interactions") or []
        spread_events = artifacts.get("spread_events") or []
        dynamic_edges = artifacts.get("dynamic_edge_events") or []
        map_grounding = self._map_grounding_context(bundle)
        map_grounding_summary = self._format_map_grounding(map_grounding)

        total_nodes = len(agents) + len(regions) + len(subregions) + len(risk_objects)
        total_edges = (
            len(config.get("transport_edges") or [])
            + len(config.get("agent_relationship_graph") or [])
            + len(dynamic_edges)
        )
        envfish_available = bool(config.get("engine_mode") == "envfish" or artifacts.get("round_snapshots") or latest)

        return {
            "simulation_id": simulation_id,
            "simulation_kind": "envfish" if envfish_available else "generic",
            "envfish_available": envfish_available,
            "graph_id": graph_id,
            "simulation_requirement": simulation_requirement,
            "total_entities": len(agents),
            "graph_statistics": {
                "graph_id": graph_id,
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "entity_types": {
                    "agent": len(agents),
                    "region": len(regions),
                    "subregion": len(subregions),
                    "risk_object": len(risk_objects),
                },
            },
            "envfish": {
                "engine_mode": config.get("engine_mode") or state.get("engine_mode"),
                "scenario_mode": config.get("scenario_mode") or state.get("scenario_mode"),
                "diffusion_template": config.get("diffusion_template") or state.get("diffusion_template"),
                "map_grounding": map_grounding,
                "map_grounding_summary": map_grounding_summary,
                "total_rounds": (config.get("time_config") or {}).get("total_rounds") or state.get("configured_total_rounds"),
                "minutes_per_round": (config.get("time_config") or {}).get("minutes_per_round") or state.get("configured_minutes_per_round"),
                "agents_count": len(agents),
                "regions_count": len(regions),
                "subregions_count": len(subregions),
                "risk_objects_count": len(risk_objects),
                "interactions_count": len(interactions),
                "spread_events_count": len(spread_events),
                "latest_round": latest.get("round"),
                "latest_regions": self._region_rows(latest.get("regions") or regions, limit=6),
                "active_variables": config.get("injected_variables") or latest.get("active_variables") or [],
                "risk_objects": risk_objects,
            },
            "map_grounding": map_grounding,
            "map_grounding_summary": map_grounding_summary,
            "envfish_summary": self.get_envfish_summary(simulation_id, limit=8),
            "envfish_fact_bullets": self._fact_bullets(simulation_id, limit=12),
            "related_facts": self._fact_bullets(simulation_id, limit=12),
        }

    def get_envfish_summary(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_bundle(simulation_id)
        config = bundle.get("config") or {}
        artifacts = bundle.get("artifacts") or {}
        latest = self._latest_snapshot(bundle)
        lines = [
            f"模拟ID: {simulation_id}",
            f"场景: {config.get('scenario_mode') or 'baseline_mode'} / {config.get('diffusion_template') or 'marine'}",
            f"轮次: {latest.get('round') or len(artifacts.get('round_snapshots') or [])}/{(config.get('time_config') or {}).get('total_rounds') or '-'}",
            (
                f"规模: {len(config.get('agent_configs') or [])} 个Agent，"
                f"{len(config.get('region_graph') or [])} 个区域，"
                f"{len(config.get('subregion_graph') or [])} 个子区域，"
                f"{len(config.get('risk_objects') or [])} 个风险对象"
            ),
        ]
        map_summary = self._format_map_grounding(self._map_grounding_context(bundle))
        if map_summary:
            lines.append(map_summary)
        variables = config.get("injected_variables") or latest.get("active_variables") or []
        if variables:
            lines.append("注入变量: " + "；".join(self._variable_label(item) for item in variables[:limit]))
        risk_objects = config.get("risk_objects") or artifacts.get("risk_objects") or []
        if risk_objects:
            lines.append("核心风险: " + "；".join((item.get("title") or item.get("summary") or "") for item in risk_objects[:3] if isinstance(item, dict)))
        for item in self._region_rows(latest.get("regions") or config.get("region_graph") or [], limit=limit):
            lines.append(
                f"区域 {item['name']}: 脆弱性 {item['vulnerability_score']}，"
                f"扩散压力 {item['spread_pressure']}，生态完整性 {item['ecosystem_integrity']}，"
                f"响应能力 {item['response_capacity']}。"
            )
        return "\n".join(line for line in lines if line)

    def get_envfish_regional_spread_summary(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_bundle(simulation_id)
        artifacts = bundle.get("artifacts") or {}
        latest = self._latest_snapshot(bundle)
        rows = []
        for item in (artifacts.get("spread_events") or [])[-limit:]:
            rows.append(
                f"R{item.get('round')}: {item.get('source_region')} -> {item.get('target_region')}，"
                f"强度 {self._num(item.get('transfer_intensity'))}，滞后 {item.get('delay_rounds', '-')} 轮，"
                f"置信度 {self._num(item.get('confidence'))}。"
            )
        diffusion = latest.get("diffusion") or {}
        next_regions = diffusion.get("likely_next_impacted_regions") or []
        if next_regions:
            rows.append("后续可能受影响区域: " + "、".join(map(str, next_regions[:limit])))
        if not rows:
            rows.extend(
                f"{item['name']}: 扩散压力 {item['spread_pressure']}，暴露 {item['exposure_score']}。"
                for item in self._region_rows(latest.get("regions") or [], limit=limit)
            )
        return "\n".join(rows) or "暂无区域扩散摘要。"

    def get_envfish_vulnerability_ranking(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_bundle(simulation_id)
        latest = self._latest_snapshot(bundle)
        ranking = latest.get("vulnerability_ranking") or latest.get("top_regions") or latest.get("regions") or []
        rows = self._region_rows(ranking, limit=limit, sort_key="vulnerability_score")
        if not rows:
            return "暂无脆弱性排名。"
        return "\n".join(
            f"{idx + 1}. {item['name']}: 脆弱性 {item['vulnerability_score']}，暴露 {item['exposure_score']}，"
            f"扩散压力 {item['spread_pressure']}，生态完整性 {item['ecosystem_integrity']}，响应能力 {item['response_capacity']}。"
            for idx, item in enumerate(rows)
        )

    def get_envfish_feedback_summary(self, simulation_id: str, limit: int = 8) -> str:
        latest = self._latest_snapshot(self._load_bundle(simulation_id))
        feedback = latest.get("feedback") or {}
        rows = []
        for item in (feedback.get("ecological_impacts") or [])[:limit]:
            rows.append(f"{item.get('region_name') or item.get('region_id')}: {item.get('note')}")
        for item in (feedback.get("feedback_propagation") or [])[:limit]:
            rows.append(f"{item.get('region_name') or item.get('region_id')}反馈: {item.get('loop')}")
        for item in (feedback.get("actor_decisions") or [])[:limit]:
            rows.append(f"{item.get('agent_name')}: {item.get('action_type')}，{item.get('rationale')}")
        return "\n".join(row for row in rows if row) or "暂无反馈回路摘要。"

    def get_envfish_intervention_comparison(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_bundle(simulation_id)
        config = bundle.get("config") or {}
        artifacts = bundle.get("artifacts") or {}
        latest = self._latest_snapshot(bundle)
        rows = []
        for item in (config.get("injected_variables") or latest.get("active_variables") or [])[:limit]:
            rows.append(
                f"{item.get('name') or item.get('variable_id')}: {item.get('type') or 'variable'}，"
                f"强度 {self._num(item.get('intensity_0_100') or item.get('intensity'))}，"
                f"持续 {item.get('duration_rounds', '-')} 轮；{item.get('description') or ''}"
            )
        for item in (artifacts.get("interventions") or [])[-limit:]:
            rows.append(f"R{item.get('round')}: {item.get('summary') or item.get('description') or item}")
        if not rows:
            rows.append("当前没有单独的政策干预记录；报告应将注入变量视作情景压力，并说明干预对比尚需后续实验。")
        return "\n".join(rows)

    def _load_bundle(self, simulation_id: str) -> Dict[str, Any]:
        if not simulation_id:
            return {"state": {}, "config": {}, "artifacts": {}}
        if simulation_id in self._bundle_cache:
            return self._bundle_cache[simulation_id]
        try:
            from .simulation_manager import SimulationManager
            from .simulation_runner import SimulationRunner

            manager = SimulationManager()
            state_obj = manager.get_simulation(simulation_id)
            state = state_obj.to_dict() if state_obj else {}
            config = manager.get_simulation_config(simulation_id) or {}
            artifacts = SimulationRunner.get_envfish_artifacts(simulation_id) or {}
            bundle = {"state": state, "config": config, "artifacts": artifacts}
        except Exception:
            bundle = {"state": {}, "config": {}, "artifacts": {}}
        self._bundle_cache[simulation_id] = bundle
        return bundle

    def _latest_snapshot(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = bundle.get("artifacts") or {}
        latest = artifacts.get("latest_snapshot") or {}
        if latest:
            return latest
        snapshots = artifacts.get("round_snapshots") or []
        return snapshots[-1] if snapshots else {}

    def _fact_bullets(self, simulation_id: str, limit: int = 12) -> List[str]:
        rows = []
        bundle = self._load_bundle(simulation_id)
        map_summary = self._format_map_grounding(self._map_grounding_context(bundle))
        if map_summary:
            rows.extend(map_summary.splitlines())
        summary = self.get_envfish_summary(simulation_id, limit=4)
        if summary:
            rows.extend(summary.splitlines())
        rows.extend(self.get_envfish_regional_spread_summary(simulation_id, limit=4).splitlines())
        rows.extend(self.get_envfish_feedback_summary(simulation_id, limit=4).splitlines())
        return [row for row in rows if row][:limit]

    def _map_grounding_context(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        state = bundle.get("state") or {}
        config = bundle.get("config") or {}
        map_seed_id = str(state.get("map_seed_id") or config.get("map_seed_id") or "").strip()
        if not map_seed_id:
            return {}

        try:
            from .map_seed_manager import MapSeedManager

            seed = MapSeedManager.get_seed(map_seed_id) or {}
            graph = MapSeedManager.get_graph_snapshot(map_seed_id) or {}
            report_text = MapSeedManager.get_report_text(map_seed_id) or ""
        except Exception:
            return {"map_seed_id": map_seed_id}

        graph_data = graph.get("graph_data") or graph
        nodes = [node for node in (graph_data.get("nodes") or []) if isinstance(node, dict)]
        aoi = seed.get("area_of_interest") or {}
        admin = seed.get("admin_context") or {}
        input_payload = seed.get("input") or {}
        center = aoi.get("center") or {
            "lat": input_payload.get("lat"),
            "lon": input_payload.get("lon"),
        }

        def node_source(node: Dict[str, Any]) -> str:
            return str((node.get("attributes") or {}).get("source_kind") or "").strip().lower()

        def feature_payload(node: Dict[str, Any]) -> Dict[str, Any]:
            attrs = node.get("attributes") or {}
            tags = attrs.get("tags") if isinstance(attrs.get("tags"), dict) else {}
            return {
                "name": node.get("name") or "未命名点位",
                "summary": node.get("summary") or "",
                "subtype": attrs.get("subtype") or tags.get("natural") or tags.get("landuse") or attrs.get("category") or "",
                "distance_m": attrs.get("distance_m"),
                "importance": attrs.get("importance"),
                "lat": attrs.get("lat"),
                "lon": attrs.get("lon"),
                "source_kind": node_source(node),
            }

        observed = [
            feature_payload(node)
            for node in nodes
            if node_source(node) == "observed" and (node.get("attributes") or {}).get("category") != "region"
        ]
        detected = [
            feature_payload(node)
            for node in nodes
            if node_source(node) == "detected"
        ]

        def sort_key(item: Dict[str, Any]) -> tuple:
            try:
                importance = float(item.get("importance") or 0)
            except Exception:
                importance = 0
            try:
                distance = float(item.get("distance_m") or 999999)
            except Exception:
                distance = 999999
            return (-importance, distance, str(item.get("name") or ""))

        observed.sort(key=sort_key)
        detected.sort(key=sort_key)

        return {
            "map_seed_id": map_seed_id,
            "area_label": aoi.get("label") or seed.get("title") or admin.get("display_name") or "",
            "display_name": admin.get("display_name") or "",
            "city": admin.get("city") or "",
            "district": admin.get("district") or "",
            "road": admin.get("road") or "",
            "center": center,
            "radius_m": aoi.get("radius_m") or input_payload.get("radius_m"),
            "scene_classification": seed.get("scene_classification") or {},
            "environment_baseline": seed.get("environment_baseline") or {},
            "observed_features": observed[:12],
            "detected_features": detected[:8],
            "map_report_excerpt": report_text[:4000],
            "seed_summary": seed.get("summary") or "",
        }

    def _format_map_grounding(self, grounding: Dict[str, Any]) -> str:
        if not grounding:
            return ""

        center = grounding.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
        place = grounding.get("area_label") or grounding.get("display_name") or "地图选点区域"
        radius = grounding.get("radius_m") or "-"
        observed = grounding.get("observed_features") or []
        detected = grounding.get("detected_features") or []

        lines = [
            f"地图选点事实: {place}，中心点 {lat}, {lon}，分析半径 {radius} 米。",
        ]
        admin_bits = [
            grounding.get("city"),
            grounding.get("district"),
            grounding.get("road"),
        ]
        admin_line = " / ".join(str(item) for item in admin_bits if item)
        if admin_line:
            lines.append(f"行政与道路线索: {admin_line}。")
        if grounding.get("display_name"):
            lines.append(f"逆地理编码名称: {grounding['display_name']}。")

        if observed:
            feature_text = "；".join(
                f"{item.get('name')}({item.get('subtype') or '空间要素'}, 距中心约{item.get('distance_m', '-')}米)"
                for item in observed[:8]
            )
            lines.append(f"周边真实地图点位: {feature_text}。")
        if detected:
            detected_text = "；".join(
                f"{item.get('name')}({item.get('subtype') or '遥感斑块'}, 距中心约{item.get('distance_m', '-')}米)"
                for item in detected[:5]
            )
            lines.append(f"遥感/土地覆盖斑块: {detected_text}。")
        return "\n".join(lines)

    def _fact_results(self, simulation_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        return [{"name": f"工件事实 {idx + 1}", "summary": text} for idx, text in enumerate(self._fact_bullets(simulation_id, limit))]

    def _region_rows(self, source: List[Dict[str, Any]], limit: int = 8, sort_key: str = "") -> List[Dict[str, Any]]:
        rows = []
        for item in source or []:
            vector = item.get("state_vector") or {}
            rows.append(
                {
                    "name": item.get("name") or item.get("region_name") or item.get("region_id") or "未命名区域",
                    "vulnerability_score": self._num(item.get("vulnerability_score", vector.get("vulnerability_score"))),
                    "exposure_score": self._num(item.get("exposure_score", vector.get("exposure_score"))),
                    "spread_pressure": self._num(item.get("spread_pressure", vector.get("spread_pressure"))),
                    "ecosystem_integrity": self._num(item.get("ecosystem_integrity", vector.get("ecosystem_integrity"))),
                    "response_capacity": self._num(item.get("response_capacity", vector.get("response_capacity"))),
                }
            )
        if sort_key:
            rows.sort(key=lambda item: float(item.get(sort_key) or 0), reverse=True)
        return rows[:limit]

    def _variable_label(self, item: Dict[str, Any]) -> str:
        return (
            f"{item.get('name') or item.get('variable_id')} "
            f"({item.get('type') or 'variable'}, 强度 {self._num(item.get('intensity_0_100') or item.get('intensity'))})"
        )

    def _num(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return "-"

    def _simulation_id_from_context(self, text: str) -> str:
        if not text:
            return ""
        marker = "simulation_id="
        if marker not in text:
            return ""
        return text.split(marker, 1)[1].split()[0].strip()
