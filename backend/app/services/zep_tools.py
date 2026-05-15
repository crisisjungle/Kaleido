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
class InterviewResult(SearchResult):
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

    def interview_agents(self, simulation_id: str, interview_requirement: str, simulation_requirement: str = "", max_agents: int = 5) -> InterviewResult:
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
                        f"围绕“{interview_requirement}”，该角色位于{region or '未标注区域'}；"
                        f"脆弱性 {self._num(vector.get('vulnerability_score'))}，"
                        f"恐慌 {self._num(vector.get('panic_level'))}，"
                        f"响应能力 {self._num(vector.get('response_capacity'))}。"
                    ),
                }
            )
        for item in interactions[: max(0, max_agents - len(results))]:
            results.append(
                {
                    "name": item.get("source_agent_name") or "交互样本",
                    "summary": item.get("rationale") or item.get("action_type") or "",
                }
            )
        return InterviewResult(query=interview_requirement, results=results)

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
        summary = self.get_envfish_summary(simulation_id, limit=4)
        if summary:
            rows.extend(summary.splitlines())
        rows.extend(self.get_envfish_regional_spread_summary(simulation_id, limit=4).splitlines())
        rows.extend(self.get_envfish_feedback_summary(simulation_id, limit=4).splitlines())
        return [row for row in rows if row][:limit]

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
