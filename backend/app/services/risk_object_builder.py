"""
Risk object construction for EnvFish.

Builds a compact set of reusable risk objects from graph-derived entities,
regions, actor profiles, and injected variables.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .envfish_models import (
    EnvAgentProfile,
    InjectedVariable,
    RegionNode,
    RiskAffectedCluster,
    RiskEvidence,
    RiskInterventionOption,
    RiskObject,
    RiskObjectBuildResult,
    RiskScenarioBranch,
    clamp_probability,
    clamp_score,
    ensure_unique_slug,
    score_band,
)
from .zep_entity_reader import EntityNode

logger = get_logger("envfish.risk_object_builder")


class RiskObjectBuilder:
    """Build deterministic risk objects around the current EnvFish scenario."""

    def build(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        regions: List[RegionNode],
        profiles: List[EnvAgentProfile],
        injected_variables: Optional[List[InjectedVariable]] = None,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
    ) -> RiskObjectBuildResult:
        del document_text  # reserved for future richer builders
        injected_variables = injected_variables or []
        risk_specs = self._candidate_specs(
            simulation_requirement=simulation_requirement,
            profiles=profiles,
            injected_variables=injected_variables,
        )

        risk_objects = [
            self._build_object(
                index=index,
                spec=spec,
                simulation_requirement=simulation_requirement,
                entities=entities,
                regions=regions,
                profiles=profiles,
                injected_variables=injected_variables,
                scenario_mode=scenario_mode,
                diffusion_template=diffusion_template,
            )
            for index, spec in enumerate(risk_specs, 1)
        ]

        primary_risk_object_id = ""
        if risk_objects:
            ranked = sorted(
                risk_objects,
                key=lambda item: (
                    item.severity_score,
                    item.actionability_score,
                    item.confidence_score,
                ),
                reverse=True,
            )
            primary_risk_object_id = ranked[0].risk_object_id

        notes = [
            f"Built {len(risk_objects)} risk objects from {len(entities)} entities, {len(regions)} regions, and {len(profiles)} actor profiles.",
            f"Primary mode inferred as {'incident' if injected_variables else 'watch'}.",
            "Risk objects compress graph structure into threat-oriented units for branch comparison and report grounding.",
        ]

        return RiskObjectBuildResult(
            risk_objects=risk_objects,
            primary_risk_object_id=primary_risk_object_id,
            generation_notes=notes,
        )

    def _candidate_specs(
        self,
        simulation_requirement: str,
        profiles: List[EnvAgentProfile],
        injected_variables: List[InjectedVariable],
    ) -> List[Dict[str, Any]]:
        del simulation_requirement
        specs: List[Dict[str, Any]] = [
            {
                "key": "eco_social_cascade",
                "title_hint": "生态-生计级联风险",
                "summary_focus": "环境压力如何沿着生态、收入、情绪和治理链路扩散。",
                "chain_steps": [
                    "环境压力上升",
                    "生态受体受损",
                    "生计稳定性下降",
                    "社区信任与情绪波动",
                    "治理响应压力上升",
                ],
                "branch_focus": ["生态完整性", "生计稳定性", "脆弱性变化"],
            }
        ]

        if any(profile.node_family in {"HumanActor", "OrganizationActor"} for profile in profiles):
            specs.append(
                {
                    "key": "market_trust_stress",
                    "title_hint": "市场-信任错配风险",
                    "summary_focus": "资源或安全感知变化如何先影响市场行为、消费信心和脆弱人群。",
                    "chain_steps": [
                        "风险感知或供给变化",
                        "市场与流动行为调整",
                        "收入与价格压力累积",
                        "信任/恐慌错位放大",
                        "次生社会压力扩散",
                    ],
                    "branch_focus": ["价格与收入波动", "公众信任", "脆弱人群错配"],
                }
            )

        if injected_variables or any(profile.node_family == "GovernmentActor" for profile in profiles):
            specs.append(
                {
                    "key": "governance_response_friction",
                    "title_hint": "治理响应摩擦风险",
                    "summary_focus": "政策动作、执法和信息披露如何改变风险链的节奏与分配后果。",
                    "chain_steps": [
                        "政策或应急动作落地",
                        "执行与合规摩擦出现",
                        "成本在不同群体间重新分配",
                        "信任与协调能力变化",
                        "治理系统稳态或反噬",
                    ],
                    "branch_focus": ["治理摩擦", "受益/受损群体", "二阶副作用"],
                }
            )

        return specs[:3]

    def _build_object(
        self,
        index: int,
        spec: Dict[str, Any],
        simulation_requirement: str,
        entities: List[EntityNode],
        regions: List[RegionNode],
        profiles: List[EnvAgentProfile],
        injected_variables: List[InjectedVariable],
        scenario_mode: str,
        diffusion_template: str,
    ) -> RiskObject:
        del index
        mode = "incident" if injected_variables or scenario_mode == "crisis_mode" else "watch"
        used: set[str] = set()
        risk_object_id = ensure_unique_slug(f"risk_{spec['key']}", used)
        selected_regions = self._select_regions(regions, injected_variables)
        selected_entities = self._select_entities(entities)
        selected_profiles = self._select_profiles(profiles, selected_regions)

        title = self._compose_title(spec["title_hint"], selected_regions, diffusion_template)
        severity_score = self._severity_score(selected_regions, injected_variables, selected_profiles)
        confidence_score = self._confidence_score(selected_entities, selected_regions, selected_profiles)
        actionability_score = self._actionability_score(injected_variables, selected_profiles, mode)
        novelty_score = self._novelty_score(injected_variables, selected_entities)
        turning_points = self._turning_points(spec["key"], injected_variables, selected_profiles)
        amplifiers = self._amplifiers(selected_profiles, injected_variables, diffusion_template)
        buffers = self._buffers(selected_profiles, mode)
        evidence = self._build_evidence(
            spec_key=spec["key"],
            entities=selected_entities,
            regions=selected_regions,
            chain_steps=spec["chain_steps"],
        )
        clusters = self._build_clusters(
            spec_key=spec["key"],
            profiles=selected_profiles,
            selected_regions=selected_regions,
        )
        interventions = self._build_interventions(
            spec_key=spec["key"],
            injected_variables=injected_variables,
            selected_clusters=clusters,
            mode=mode,
        )
        branches = self._build_branches(
            spec_key=spec["key"],
            interventions=interventions,
            branch_focus=spec["branch_focus"],
            mode=mode,
        )

        region_names = [region.name for region in selected_regions] or [region.name for region in regions[:2]]
        why_now = self._why_now(
            selected_regions=selected_regions,
            injected_variables=injected_variables,
            amplifiers=amplifiers,
            mode=mode,
        )
        summary = (
            f"{title}：围绕 {', '.join(region_names[:3])} 的 {spec['summary_focus']}"
            f" 当前重点在于识别转折点、错配受损者与可比较的干预路径。"
        )

        return RiskObject(
            risk_object_id=risk_object_id,
            title=title,
            summary=summary,
            why_now=why_now,
            risk_type=spec["key"],
            mode=mode,
            status="active" if mode == "incident" else "candidate",
            time_horizon="72h" if mode == "incident" else "30d",
            region_scope=region_names,
            primary_regions=region_names[:2],
            severity_score=severity_score,
            confidence_score=confidence_score,
            actionability_score=actionability_score,
            novelty_score=novelty_score,
            root_pressures=self._root_pressures(selected_entities, injected_variables, simulation_requirement),
            chain_steps=spec["chain_steps"],
            turning_points=turning_points,
            amplifiers=amplifiers,
            buffers=buffers,
            source_entity_uuids=[entity.uuid for entity in selected_entities],
            source_variable_ids=[item.variable_id for item in injected_variables],
            evidence=evidence,
            affected_clusters=clusters,
            intervention_options=interventions,
            scenario_branches=branches,
        )

    def _select_regions(self, regions: List[RegionNode], injected_variables: List[InjectedVariable]) -> List[RegionNode]:
        region_lookup = {item.region_id: item for item in regions}
        selected: List[RegionNode] = []
        for variable in injected_variables:
            for region_id in variable.target_regions[:2]:
                region = region_lookup.get(region_id)
                if region and region not in selected:
                    selected.append(region)
        if selected:
            primary = list(selected)
            for region in list(selected):
                for neighbor_id in region.neighbors[:1]:
                    neighbor = region_lookup.get(neighbor_id)
                    if neighbor and neighbor not in primary:
                        primary.append(neighbor)
            return primary[:3]
        ranked = sorted(
            regions,
            key=lambda item: (
                item.state_vector.get("vulnerability_score", 0.0),
                item.state_vector.get("spread_pressure", 0.0),
            ),
            reverse=True,
        )
        return ranked[:3]

    def _select_entities(self, entities: List[EntityNode]) -> List[EntityNode]:
        if not entities:
            return []
        selected = [entity for entity in entities if entity.related_edges][:8]
        return selected or entities[:8]

    def _select_profiles(self, profiles: List[EnvAgentProfile], selected_regions: List[RegionNode]) -> List[EnvAgentProfile]:
        allowed_regions = {region.region_id for region in selected_regions}
        scoped = [profile for profile in profiles if profile.primary_region in allowed_regions]
        selected = scoped or list(profiles)
        grouped: Dict[str, List[EnvAgentProfile]] = defaultdict(list)
        for profile in selected:
            grouped[profile.agent_type or profile.node_family].append(profile)

        ordered: List[EnvAgentProfile] = []
        max_group = max((len(items) for items in grouped.values()), default=0)
        for index in range(max_group):
            for items in grouped.values():
                if index < len(items):
                    ordered.append(items[index])
        return ordered[:18]

    def _compose_title(self, title_hint: str, selected_regions: List[RegionNode], diffusion_template: str) -> str:
        if selected_regions:
            return f"{selected_regions[0].name}{title_hint}"
        return f"{diffusion_template}场景{title_hint}"

    def _severity_score(
        self,
        selected_regions: List[RegionNode],
        injected_variables: List[InjectedVariable],
        selected_profiles: List[EnvAgentProfile],
    ) -> float:
        region_score = 0.0
        if selected_regions:
            region_score = sum(region.state_vector.get("vulnerability_score", 0.0) for region in selected_regions) / len(selected_regions)
        variable_score = 0.0
        if injected_variables:
            variable_score = sum(item.intensity_0_100 for item in injected_variables) / len(injected_variables)
        profile_score = 0.0
        if selected_profiles:
            profile_score = sum(profile.state_vector.get("vulnerability_score", 0.0) for profile in selected_profiles) / len(selected_profiles)
        return clamp_score(region_score * 0.45 + variable_score * 0.35 + profile_score * 0.2)

    def _confidence_score(
        self,
        selected_entities: List[EntityNode],
        selected_regions: List[RegionNode],
        selected_profiles: List[EnvAgentProfile],
    ) -> float:
        evidence_density = min(1.0, len(selected_entities) / 8)
        region_density = min(1.0, len(selected_regions) / 3)
        cluster_density = min(1.0, len(selected_profiles) / 8)
        return clamp_probability(0.35 + evidence_density * 0.3 + region_density * 0.2 + cluster_density * 0.15)

    def _actionability_score(
        self,
        injected_variables: List[InjectedVariable],
        selected_profiles: List[EnvAgentProfile],
        mode: str,
    ) -> float:
        score = 42.0
        if mode == "incident":
            score += 18
        if injected_variables:
            score += 12
        if any(profile.node_family == "GovernmentActor" for profile in selected_profiles):
            score += 12
        if any(profile.node_family == "OrganizationActor" for profile in selected_profiles):
            score += 6
        return clamp_score(score)

    def _novelty_score(self, injected_variables: List[InjectedVariable], selected_entities: List[EntityNode]) -> float:
        score = 28.0
        if injected_variables:
            score += 20
        if len(selected_entities) >= 5:
            score += 10
        if any(entity.related_edges for entity in selected_entities[:4]):
            score += 8
        return clamp_score(score)

    def _root_pressures(
        self,
        selected_entities: List[EntityNode],
        injected_variables: List[InjectedVariable],
        simulation_requirement: str,
    ) -> List[str]:
        pressures = [item.name for item in injected_variables[:3]]
        for entity in selected_entities[:4]:
            if entity.name and entity.name not in pressures:
                pressures.append(entity.name)
        if not pressures and simulation_requirement:
            pressures.append(simulation_requirement[:64])
        return pressures[:5]

    def _turning_points(
        self,
        spec_key: str,
        injected_variables: List[InjectedVariable],
        selected_profiles: List[EnvAgentProfile],
    ) -> List[str]:
        points: List[str] = []
        for variable in injected_variables[:2]:
            points.append(f"{variable.name} 在第 {variable.start_round} 轮进入场景并可能改写链路节奏")
        if spec_key == "market_trust_stress":
            points.append("当价格或安全感知先于生态指标变化时，风险会转向市场与信任")
        if spec_key == "governance_response_friction":
            points.append("政策动作是否同步补偿与披露，将决定治理摩擦是缓和还是放大")
        if any(profile.node_family == "GovernmentActor" for profile in selected_profiles):
            points.append("治理响应能力与公众信任同步变化时，系统可能跨过协调阈值")
        return points[:4]

    def _amplifiers(
        self,
        selected_profiles: List[EnvAgentProfile],
        injected_variables: List[InjectedVariable],
        diffusion_template: str,
    ) -> List[str]:
        amplifiers = [f"{diffusion_template}扩散路径"]
        if injected_variables:
            amplifiers.append("外生变量强度叠加")
        if any(profile.node_family == "HumanActor" for profile in selected_profiles):
            amplifiers.append("脆弱人群的生计依赖")
        if any(profile.node_family == "OrganizationActor" for profile in selected_profiles):
            amplifiers.append("市场与信息传播的二阶放大")
        if any(profile.node_family == "GovernmentActor" for profile in selected_profiles):
            amplifiers.append("政策执行摩擦")
        return amplifiers[:4]

    def _buffers(self, selected_profiles: List[EnvAgentProfile], mode: str) -> List[str]:
        buffers = ["区域服务能力", "社区适应与替代收入"]
        if any(profile.node_family == "GovernmentActor" for profile in selected_profiles):
            buffers.append("治理响应与公开沟通")
        if any(profile.node_family == "OrganizationActor" for profile in selected_profiles):
            buffers.append("机构协同与公益支持")
        if mode == "watch":
            buffers.append("提前监测与转折点预警")
        return buffers[:4]

    def _build_evidence(
        self,
        spec_key: str,
        entities: List[EntityNode],
        regions: List[RegionNode],
        chain_steps: List[str],
    ) -> List[RiskEvidence]:
        evidence: List[RiskEvidence] = []
        for index, region in enumerate(regions[:3], 1):
            evidence.append(
                RiskEvidence(
                    evidence_id=f"{spec_key}_region_{index}",
                    source_type="region_snapshot",
                    title=f"{region.name} 区域基线",
                    summary=region.description or f"{region.name} 提供当前风险对象的区域上下文。",
                    confidence=0.72,
                    source_ref=region.region_id,
                    related_chain_steps=chain_steps[:2],
                    region_scope=[region.name],
                )
            )
        for index, entity in enumerate(entities[:5], 1):
            facts = [item.get("fact", "") for item in entity.related_edges[:2] if item.get("fact")]
            evidence.append(
                RiskEvidence(
                    evidence_id=f"{spec_key}_entity_{index}",
                    source_type="entity_summary",
                    title=entity.name,
                    summary=entity.summary or entity.attributes.get("description") or entity.get_entity_type() or entity.name,
                    confidence=0.63,
                    source_ref=entity.uuid,
                    related_chain_steps=chain_steps[1:4],
                    entity_refs=[entity.uuid],
                    extracted_facts=facts[:2],
                )
            )
        return evidence[:8]

    def _build_clusters(
        self,
        spec_key: str,
        profiles: List[EnvAgentProfile],
        selected_regions: List[RegionNode],
    ) -> List[RiskAffectedCluster]:
        grouped: Dict[str, List[EnvAgentProfile]] = defaultdict(list)
        region_lookup = {region.region_id: region.name for region in selected_regions}
        for profile in profiles:
            key = f"{profile.profession}:{profile.primary_region}"
            grouped[key].append(profile)

        clusters: List[RiskAffectedCluster] = []
        used: set[str] = set()
        for key, items in list(grouped.items())[:6]:
            del key
            sample = items[0]
            cluster_id = ensure_unique_slug(f"{spec_key}_{sample.profession}_{sample.primary_region}", used)
            dependency_profile = list(sample.goals[:2])
            if sample.primary_region:
                dependency_profile.append(f"依赖 {region_lookup.get(sample.primary_region, sample.primary_region)} 区域状态")
            early_loss = list(sample.sensitivities[:3]) or ["生计稳定性先于显性灾情恶化", "情绪与信任可能提前失衡"]
            vulnerability = 0.0
            if items:
                vulnerability = sum(item.state_vector.get("vulnerability_score", 0.0) for item in items) / len(items)
            mismatch = vulnerability * 0.55 + (12 if sample.node_family == "HumanActor" else 4)
            clusters.append(
                RiskAffectedCluster(
                    cluster_id=cluster_id,
                    name=f"{sample.profession}@{region_lookup.get(sample.primary_region, sample.primary_region)}",
                    cluster_type=sample.node_family,
                    primary_regions=[region_lookup.get(sample.primary_region, sample.primary_region)],
                    actor_ids=[item.agent_id for item in items],
                    dependency_profile=dependency_profile[:4],
                    early_loss_signals=early_loss[:4],
                    vulnerability_score=vulnerability,
                    mismatch_risk=mismatch,
                    notes=f"由 {len(items)} 个同类角色合并而成的风险人群簇。",
                )
            )
        return clusters[:5]

    def _build_interventions(
        self,
        spec_key: str,
        injected_variables: List[InjectedVariable],
        selected_clusters: List[RiskAffectedCluster],
        mode: str,
    ) -> List[RiskInterventionOption]:
        interventions: List[RiskInterventionOption] = []
        used: set[str] = set()
        if injected_variables:
            for variable in injected_variables[:3]:
                if variable.type != "policy" and not variable.policy_mode:
                    continue
                intervention_id = ensure_unique_slug(f"{spec_key}_{variable.name}", used)
                interventions.append(
                    RiskInterventionOption(
                        intervention_id=intervention_id,
                        name=variable.name,
                        policy_type=variable.policy_mode or "monitor",
                        description=variable.description or f"基于 {variable.name} 的政策分支。",
                        target_chain_steps=["政策或应急动作落地", "信任与协调能力变化"],
                        expected_direct_effects=["缩短高风险链的可见反应时间", "改变脆弱群体受损顺序"],
                        expected_second_order_effects=["可能放大合规成本", "可能改变市场与情绪预期"],
                        benefit_clusters=[cluster.name for cluster in selected_clusters[:2]],
                        hurt_clusters=[cluster.name for cluster in selected_clusters[2:4]],
                        friction_points=["执行一致性", "公众接受度"],
                        confidence=0.58,
                        source_variable_id=variable.variable_id,
                    )
                )
        if not interventions:
            defaults = [
                ("加强监测与披露", "monitor"),
                ("限制高风险活动", "restrict"),
                ("补偿与缓冲支持", "subsidize"),
            ]
            for name, mode_name in defaults:
                intervention_id = ensure_unique_slug(f"{spec_key}_{mode_name}", used)
                interventions.append(
                    RiskInterventionOption(
                        intervention_id=intervention_id,
                        name=name,
                        policy_type=mode_name,
                        description=f"{name} 用于控制 {spec_key} 风险链的扩散或分配后果。",
                        target_chain_steps=["环境压力上升", "社区信任与情绪波动"],
                        expected_direct_effects=["提高可观测性", "降低高脆弱区域的暴露升级速度"],
                        expected_second_order_effects=["可能转移成本", "可能延后而非消除风险"],
                        benefit_clusters=[cluster.name for cluster in selected_clusters[:2]],
                        hurt_clusters=[cluster.name for cluster in selected_clusters[2:3]],
                        friction_points=["资源约束", "执行摩擦"],
                        confidence=0.55 if mode == "watch" else 0.62,
                    )
                )
        return interventions[:3]

    def _build_branches(
        self,
        spec_key: str,
        interventions: List[RiskInterventionOption],
        branch_focus: List[str],
        mode: str,
    ) -> List[RiskScenarioBranch]:
        branches = [
            RiskScenarioBranch(
                branch_id=f"{spec_key}_baseline",
                name="baseline",
                description="不额外注入新干预，观察当前风险链自然演化。",
                assumptions=["沿用当前区域与角色基线", "仅保留既有外生变量"],
                comparison_focus=branch_focus,
                branch_type="baseline",
            )
        ]
        if interventions:
            first = interventions[0]
            branches.append(
                RiskScenarioBranch(
                    branch_id=f"{spec_key}_targeted_action",
                    name="targeted_action",
                    description=f"优先测试 {first.name} 对风险链的缓冲效果。",
                    assumptions=["只注入一个优先干预", "优先观察直接效果与二阶副作用"],
                    target_interventions=[first.intervention_id],
                    comparison_focus=branch_focus,
                    branch_type="targeted",
                )
            )
        if len(interventions) >= 2:
            combo = interventions[:2]
            branches.append(
                RiskScenarioBranch(
                    branch_id=f"{spec_key}_combined_response",
                    name="combined_response",
                    description="测试双干预组合下的协同与摩擦。",
                    assumptions=["组合干预可能带来协同也可能带来治理摩擦"],
                    target_interventions=[item.intervention_id for item in combo],
                    comparison_focus=branch_focus + ["组合摩擦"],
                    branch_type="combined",
                )
            )
        if mode == "incident":
            branches.append(
                RiskScenarioBranch(
                    branch_id=f"{spec_key}_delayed_response",
                    name="delayed_response",
                    description="测试响应迟滞时，风险链是否跨过关键转折点。",
                    assumptions=["响应晚于关键窗口", "弱信号在短期内持续积累"],
                    comparison_focus=branch_focus + ["转折点窗口"],
                    branch_type="stress",
                )
            )
        return branches[:4]

    def _why_now(
        self,
        selected_regions: List[RegionNode],
        injected_variables: List[InjectedVariable],
        amplifiers: List[str],
        mode: str,
    ) -> str:
        if injected_variables:
            variable_names = ", ".join(item.name for item in injected_variables[:2])
            return f"{variable_names} 已进入场景，且 {', '.join(amplifiers[:2])} 正在提高风险链的扩散与分配后果。"
        if selected_regions:
            region = selected_regions[0]
            band = score_band(region.state_vector.get("vulnerability_score", 0.0))
            return f"{region.name} 当前脆弱性处于 {band} 区间，{', '.join(amplifiers[:2])} 让该链路具备持续恶化的条件。"
        return f"当前场景已具备 {', '.join(amplifiers[:2])} 等放大条件，需要提前识别转折点。"
