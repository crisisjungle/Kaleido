import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class RiskBuildResult:
    risk_definitions: List[Dict[str, Any]]
    primary_risk_id: str
    generation_notes: List[str]


class RiskDefinitionBuilder:
    """Build risk objects from the existing scenario graph inputs.

    This stays deterministic on purpose: Step 2 needs useful risk previews even
    before the deeper simulation runtime has produced dynamic evidence.
    """

    RISK_TEMPLATES = [
        {
            "key": "water_ecology",
            "title": "水位与生态服务耦合风险",
            "risk_type": "ecological_coupling",
            "keywords": ["水", "湿地", "水库", "河", "湖", "海", "湾", "滨海", "生态", "森林", "公园", "绿地", "water", "wetland", "reservoir", "coast"],
            "chain_steps": ["外部灾害触发", "水位与径流压力上升", "生态缓冲能力下降", "居民安全与城市功能受影响"],
            "turning_points": ["关键水体或湿地从缓冲空间转为风险传播节点", "生态服务下降开始影响周边居民与设施"],
            "dependencies": ["水位/径流", "生态缓冲", "水体连通", "周边开放空间"],
            "signals": ["水位持续上升", "湿地蓄滞能力接近阈值", "公园或绿地封闭需求增加"],
        },
        {
            "key": "urban_flood",
            "title": "建成区内涝与排水压力风险",
            "risk_type": "urban_flooding",
            "keywords": ["台风", "暴雨", "洪", "涝", "排水", "低洼", "城区", "建成区", "道路积水", "storm", "rain", "flood", "drainage"],
            "chain_steps": ["强降雨或风暴潮触发", "低洼片区汇水", "排水与道路承载不足", "通行和应急处置受阻"],
            "turning_points": ["排水能力低于降雨汇流强度", "道路积水开始阻断关键通行路径"],
            "dependencies": ["排水能力", "道路通行", "低洼地形", "应急响应窗口"],
            "signals": ["短时降雨强度升高", "低洼道路积水", "排水口或泵站压力升高"],
        },
        {
            "key": "public_exposure",
            "title": "居民与游客暴露风险",
            "risk_type": "population_exposure",
            "keywords": ["居民", "游客", "人群", "社区", "学校", "医院", "安全", "避险", "疏散", "resident", "tourist", "population", "public"],
            "chain_steps": ["预警信息触达", "暴露人群活动路径变化", "避险与服务需求集中", "脆弱人群安全风险上升"],
            "turning_points": ["人群仍停留在高暴露区域", "避险、转移或服务需求超过现场承载"],
            "dependencies": ["预警触达", "避险空间", "公共服务", "脆弱人群支持"],
            "signals": ["游客滞留", "居民求助增加", "避险点或热线需求上升"],
        },
        {
            "key": "infrastructure_access",
            "title": "交通与关键设施可达性风险",
            "risk_type": "infrastructure_access",
            "keywords": ["交通", "道路", "桥", "隧", "站", "港", "电力", "通信", "设施", "救援", "transport", "road", "facility", "rescue"],
            "chain_steps": ["灾害影响关键设施", "道路或通信节点受限", "救援和维护到达时间拉长", "次生服务风险扩大"],
            "turning_points": ["关键道路或设施节点不可达", "救援维护响应时间超过场景窗口"],
            "dependencies": ["道路网络", "设施运维", "通信联络", "救援资源"],
            "signals": ["通行中断", "设施告警", "维护工单积压"],
        },
        {
            "key": "response_capacity",
            "title": "预警响应与公共服务承压风险",
            "risk_type": "response_capacity",
            "keywords": ["预警", "应急", "响应", "调度", "治理", "公共服务", "热线", "资源", "warning", "emergency", "response"],
            "chain_steps": ["预警升级", "跨部门处置需求增加", "资源调度出现错配", "服务承压影响风险处置"],
            "turning_points": ["响应资源无法覆盖全部高暴露区域", "跨区域调度延迟影响关键节点处置"],
            "dependencies": ["预警规则", "应急资源", "跨区域协同", "服务容量"],
            "signals": ["处置队列增长", "跨区域协同延迟", "服务请求集中"],
        },
    ]

    def build(self, **kwargs) -> RiskBuildResult:
        variables = [self._as_dict(item) for item in (kwargs.get("injected_variables") or [])]
        regions = [
            self._as_dict(item)
            for item in [*(kwargs.get("regions") or []), *(kwargs.get("subregions") or [])]
        ]
        profiles = [self._as_dict(item) for item in (kwargs.get("profiles") or [])]
        scenario_text = self._join_text(
            kwargs.get("simulation_requirement"),
            kwargs.get("document_text"),
            kwargs.get("scenario_mode"),
            kwargs.get("diffusion_template"),
            kwargs.get("hazard_template_id"),
            *[self._join_text(item.get("name"), item.get("description"), item.get("type"), item.get("template")) for item in variables],
            *[self._join_text(item.get("name"), item.get("description"), item.get("tags"), item.get("carriers"), item.get("ecology_assets"), item.get("exposure_channels")) for item in regions],
            *[self._join_text(item.get("name"), item.get("role_type"), item.get("profession"), item.get("sensitivities"), item.get("action_space")) for item in profiles],
        )
        intensity = self._scenario_intensity(variables)

        candidates = []
        for template in self.RISK_TEMPLATES:
            matches = self._keyword_matches(scenario_text, template["keywords"])
            matched_regions = self._matching_regions(regions, template["keywords"])
            matched_profiles = self._matching_profiles(profiles, template["keywords"])
            score = len(matches) * 4 + len(matched_regions) * 3 + len(matched_profiles)
            if matches or matched_regions or matched_profiles:
                candidates.append({
                    "template": template,
                    "score": score,
                    "matches": matches,
                    "regions": matched_regions,
                    "profiles": matched_profiles,
                })

        if not candidates:
            candidates = [{
                "template": self.RISK_TEMPLATES[0],
                "score": 1,
                "matches": [],
                "regions": regions[:3],
                "profiles": profiles[:6],
            }]

        candidates.sort(key=lambda item: item["score"], reverse=True)
        selected = candidates[:5]
        if len(selected) < 3 and len(self.RISK_TEMPLATES) >= 3:
            selected_keys = {item["template"]["key"] for item in selected}
            for template in self.RISK_TEMPLATES:
                if template["key"] not in selected_keys:
                    selected.append({
                        "template": template,
                        "score": 0,
                        "matches": [],
                        "regions": self._fallback_regions(regions, template["keywords"]),
                        "profiles": self._fallback_profiles(profiles, template["keywords"]),
                    })
                    selected_keys.add(template["key"])
                if len(selected) >= 3:
                    break

        definitions = [
            self._build_definition(index, item, variables, regions, profiles, intensity, kwargs)
            for index, item in enumerate(selected)
        ]
        definitions.sort(
            key=lambda item: (
                item.get("_selection_score", 0),
                item.get("severity_score", 0),
                item.get("actionability_score", 0),
            ),
            reverse=True,
        )
        for item in definitions:
            item.pop("_selection_score", None)
        primary_id = str(definitions[0].get("risk_id") or "") if definitions else ""
        notes = [
            "风险对象由场景变量、区域标签、Agent 角色和文本关键词共同生成。",
            "严重性为 0-100 场景风险分，置信度为 0-1 证据充分度，可行动性为 0-100 干预抓手清晰度。",
        ]
        if variables:
            notes.append(f"已参考 {len(variables)} 个注入变量。")
        if regions:
            notes.append(f"已映射 {len(regions)} 个区域节点。")
        return RiskBuildResult(definitions, primary_id, notes)

    def reframe_runtime(self, existing_definitions=None, injected_variables=None, current_round=0, **kwargs) -> Dict[str, Any]:
        definitions = list(existing_definitions or [])
        created = []
        for variable in injected_variables or []:
            variable_dict = self._as_dict(variable)
            risk_id = f"risk_variable_{len(definitions) + 1}"
            intensity = self._coerce_score(variable_dict.get("intensity_0_100", variable_dict.get("intensity", 50)), default=50)
            definitions.append({
                "risk_id": risk_id,
                "title": variable_dict.get("name") or "注入变量风险",
                "summary": variable_dict.get("description") or "由运行时注入变量触发的新风险对象。",
                "status": "watch",
                "mode": "incident",
                "risk_type": variable_dict.get("type") or "variable_triggered",
                "severity_score": round(max(35, intensity), 1),
                "confidence_score": 0.66,
                "actionability_score": round(min(88, max(45, intensity * 0.78)), 1),
                "scope": {"regions": [{"region_id": item, "region_name": item} for item in variable_dict.get("target_regions") or []], "entities": [], "actors": []},
                "region_scope": variable_dict.get("target_regions") or [],
                "chain_steps": ["变量注入", "局部状态变化", "风险链路刷新"],
                "turning_points": ["注入变量强度或持续时间超过当前场景承载"],
                "root_pressures": [variable_dict.get("name") or variable_dict.get("type") or "runtime_variable"],
                "trigger_rules": {"source_variable_ids": [variable_dict.get("variable_id") or risk_id]},
                "created_round": current_round,
            })
            created.append(risk_id)
        updated = [] if created else [str(definitions[0].get("risk_id") or "risk_primary")] if definitions else []
        return {
            "risk_definitions": definitions,
            "primary_risk_id": (definitions[0].get("risk_id") if definitions else ""),
            "created_risk_ids": created,
            "updated_risk_ids": updated,
        }

    def _build_definition(
        self,
        index: int,
        candidate: Dict[str, Any],
        variables: List[Dict[str, Any]],
        all_regions: List[Dict[str, Any]],
        all_profiles: List[Dict[str, Any]],
        intensity: float,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        template = candidate["template"]
        regions = candidate.get("regions") or self._fallback_regions(all_regions, template["keywords"])
        profiles = candidate.get("profiles") or self._fallback_profiles(all_profiles, template["keywords"])
        region_refs = [self._region_ref(item) for item in regions[:6]]
        actor_refs = []
        for profile in profiles[:8]:
            actor_ref = self._actor_ref(profile)
            if actor_ref:
                actor_refs.append(actor_ref)
        source_entities = self._source_entities(profiles[:8])
        variable_names = [str(item.get("name") or item.get("type") or "").strip() for item in variables if item.get("name") or item.get("type")]
        region_names = [item["region_name"] for item in region_refs]
        evidence_confidence = self._confidence_score(candidate, variables, regions, profiles)
        severity = self._severity_score(intensity, candidate, regions, profiles)
        actionability = self._actionability_score(candidate, region_refs, actor_refs, template)
        risk_id = f"risk_{template['key']}"
        summary = self._summary(template, variable_names, region_names, kwargs.get("simulation_requirement"))
        cluster = self._cluster(template, region_names, actor_refs, severity, actionability)

        return {
            "risk_id": risk_id,
            "legacy_risk_object_id": risk_id,
            "category": "scenario_derived",
            "risk_type": template["risk_type"],
            "title": template["title"],
            "summary": summary,
            "why_now": self._why_now(template, variable_names, region_names),
            "status": "tracked",
            "mode": "watch" if index > 0 else "incident",
            "time_horizon": self._time_horizon(kwargs.get("temporal_profile") or {}),
            "priority_seed": round(max(0.1, min(1.0, severity / 100)), 3),
            "severity_score": severity,
            "confidence_score": evidence_confidence,
            "actionability_score": actionability,
            "scope": {
                "regions": region_refs,
                "entities": [{"entity_uuid": item, "entity_name": item} for item in source_entities],
                "actors": actor_refs,
            },
            "region_scope": region_names,
            "primary_regions": region_names[:2],
            "source_entity_uuids": source_entities,
            "source_actor_ids": [item["actor_id"] for item in actor_refs],
            "source_actor_names": [item["actor_name"] for item in actor_refs],
            "source_variable_ids": [str(item.get("variable_id") or "") for item in variables if item.get("variable_id")],
            "root_pressures": self._unique([*variable_names, *candidate.get("matches", []), template["risk_type"]]),
            "chain_steps": list(template["chain_steps"]),
            "turning_points": list(template["turning_points"]),
            "turning_point_candidates": list(template["turning_points"]),
            "amplifiers": self._amplifiers(template, region_names),
            "buffers": self._buffers(template, region_names),
            "affected_clusters": [cluster],
            "evidence": [self._evidence(template, candidate, region_names, source_entities)],
            "intervention_templates": self._interventions(template, region_names),
            "branch_templates": self._branches(template),
            "trigger_rules": {
                "matched_keywords": candidate.get("matches") or [],
                "minimum_signal_count": 2,
                "source": "deterministic_scenario_builder",
            },
            "_selection_score": candidate.get("score", 0),
        }

    def _summary(self, template: Dict[str, Any], variable_names: List[str], region_names: List[str], requirement: Any) -> str:
        trigger = "、".join(variable_names[:2]) or "当前场景压力"
        scope = "、".join(region_names[:4]) or "关键区域"
        return f"{trigger}作用下，{scope}可能形成{template['title']}，需要持续观察触发、传播、承压与干预窗口。"

    def _why_now(self, template: Dict[str, Any], variable_names: List[str], region_names: List[str]) -> str:
        trigger = "、".join(variable_names[:2]) or "场景变量"
        scope = "、".join(region_names[:3]) or "已生成区域"
        return f"{trigger}已与{scope}等节点建立场景关联，当前需要把{template['title']}作为独立对象跟踪。"

    def _cluster(self, template: Dict[str, Any], region_names: List[str], actor_refs: List[Dict[str, Any]], severity: float, actionability: float) -> Dict[str, Any]:
        return {
            "cluster_id": f"cluster_{template['key']}",
            "name": template["title"].replace("风险", "影响群簇"),
            "cluster_type": template["risk_type"],
            "primary_regions": region_names[:4],
            "actor_ids": [item["actor_id"] for item in actor_refs if isinstance(item.get("actor_id"), int)],
            "dependency_profile": list(template["dependencies"]),
            "early_loss_signals": list(template["signals"]),
            "vulnerability_score": round(min(100, max(20, severity * 0.92)), 1),
            "mismatch_risk": round(min(100, max(15, 100 - actionability * 0.55)), 1),
            "notes": "由风险对象生成器根据场景节点和 Agent 角色归并。",
        }

    def _evidence(self, template: Dict[str, Any], candidate: Dict[str, Any], region_names: List[str], source_entities: List[str]) -> Dict[str, Any]:
        matches = candidate.get("matches") or []
        facts = matches[:6] or [template["risk_type"]]
        return {
            "evidence_id": f"evidence_{template['key']}",
            "source_type": "scenario_config",
            "title": f"{template['title']}触发证据",
            "summary": "、".join(facts),
            "confidence": self._confidence_score(candidate, [], candidate.get("regions") or [], candidate.get("profiles") or []),
            "source_ref": "step2_scenario_generation",
            "related_chain_steps": list(template["chain_steps"][:2]),
            "region_scope": region_names[:6],
            "entity_refs": source_entities[:8],
            "extracted_facts": facts,
        }

    def _interventions(self, template: Dict[str, Any], region_names: List[str]) -> List[Dict[str, Any]]:
        first_region = region_names[0] if region_names else "关键区域"
        return [
            {
                "intervention_id": f"monitor_{template['key']}",
                "name": f"监测{first_region}早期信号",
                "policy_type": "monitor",
                "description": f"围绕{template['title']}的早期信号建立监测和复核。",
                "target_chain_steps": list(template["chain_steps"][:2]),
                "expected_direct_effects": ["更早发现风险上升", "降低误判和漏判"],
                "expected_second_order_effects": ["为后续调度留出时间窗口"],
                "benefit_clusters": [f"cluster_{template['key']}"],
                "hurt_clusters": [],
                "friction_points": ["需要持续数据更新"],
                "confidence": 0.68,
            },
            {
                "intervention_id": f"mitigate_{template['key']}",
                "name": f"压降{template['title']}",
                "policy_type": "mitigate",
                "description": "对高暴露节点提前布置资源、分流或保护措施。",
                "target_chain_steps": list(template["chain_steps"][1:3]),
                "expected_direct_effects": ["降低暴露和传播强度"],
                "expected_second_order_effects": ["减少服务挤兑和次生影响"],
                "benefit_clusters": [f"cluster_{template['key']}"],
                "hurt_clusters": [],
                "friction_points": ["可能与资源调度优先级冲突"],
                "confidence": 0.62,
            },
        ]

    def _branches(self, template: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "branch_id": f"baseline_{template['key']}",
                "name": "维持当前响应",
                "description": "按当前场景参数继续推演，不额外提前干预。",
                "assumptions": ["风险信号自然演化"],
                "target_interventions": [],
                "comparison_focus": ["风险峰值", "传播范围", "处置滞后"],
                "branch_type": "baseline",
            },
            {
                "branch_id": f"intervention_{template['key']}",
                "name": "提前监测与压降",
                "description": "提前锁定高暴露节点并启动监测、分流或保护动作。",
                "assumptions": ["监测信号可及时触发"],
                "target_interventions": [f"monitor_{template['key']}", f"mitigate_{template['key']}"],
                "comparison_focus": ["处置窗口", "影响人群", "区域扩散"],
                "branch_type": "intervention",
            },
        ]

    def _severity_score(self, intensity: float, candidate: Dict[str, Any], regions: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> float:
        coverage = min(18, len(regions) * 3 + len(profiles) * 0.8)
        match_bonus = min(12, len(candidate.get("matches") or []) * 2.5)
        return round(min(96, max(35, intensity * 0.62 + coverage + match_bonus)), 1)

    def _confidence_score(self, candidate: Dict[str, Any], variables: List[Dict[str, Any]], regions: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> float:
        score = 0.48
        score += min(0.16, len(candidate.get("matches") or []) * 0.035)
        score += 0.08 if variables else 0
        score += min(0.16, len(regions) * 0.025)
        score += min(0.08, len(profiles) * 0.01)
        return round(min(0.9, max(0.35, score)), 2)

    def _actionability_score(self, candidate: Dict[str, Any], region_refs: List[Dict[str, Any]], actor_refs: List[Dict[str, Any]], template: Dict[str, Any]) -> float:
        score = 38 + len(region_refs) * 5 + len(actor_refs) * 2 + len(template["signals"]) * 3
        if candidate.get("matches"):
            score += 8
        return round(min(92, max(35, score)), 1)

    def _scenario_intensity(self, variables: List[Dict[str, Any]]) -> float:
        values = []
        for item in variables:
            if "intensity_0_100" in item or "intensity" in item:
                values.append(self._coerce_score(item.get("intensity_0_100", item.get("intensity")), default=50))
        return max(values) if values else 62

    def _time_horizon(self, temporal_profile: Dict[str, Any]) -> str:
        total_rounds = temporal_profile.get("total_rounds")
        minutes = temporal_profile.get("minutes_per_round")
        if total_rounds and minutes:
            hours = max(1, round((float(total_rounds) * float(minutes)) / 60))
            return f"{hours}h"
        return "scenario_window"

    def _matching_regions(self, regions: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        return [item for item in regions if self._keyword_matches(self._region_text(item), keywords)]

    def _matching_profiles(self, profiles: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        return [item for item in profiles if self._keyword_matches(self._profile_text(item), keywords)]

    def _fallback_regions(self, regions: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        matched = self._matching_regions(regions, keywords)
        return matched or regions[:4]

    def _fallback_profiles(self, profiles: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        matched = self._matching_profiles(profiles, keywords)
        return matched or profiles[:6]

    def _region_ref(self, item: Dict[str, Any]) -> Dict[str, Any]:
        name = str(item.get("name") or item.get("region_name") or item.get("region_id") or "").strip()
        region_id = str(item.get("region_id") or item.get("id") or name).strip()
        return {"region_id": region_id or name, "region_name": name or region_id}

    def _actor_ref(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        raw_id = item.get("agent_id") or item.get("actor_id") or item.get("id")
        if raw_id is None:
            return None
        try:
            actor_id: int | str = int(raw_id)
        except (TypeError, ValueError):
            actor_id = str(raw_id)
        name = str(item.get("name") or item.get("username") or item.get("agent_name") or raw_id).strip()
        return {"actor_id": actor_id, "actor_name": name or str(raw_id)}

    def _source_entities(self, profiles: List[Dict[str, Any]]) -> List[str]:
        return self._unique([
            str(item.get("source_entity_uuid") or item.get("uuid") or item.get("name") or "").strip()
            for item in profiles
            if item.get("source_entity_uuid") or item.get("uuid") or item.get("name")
        ])

    def _amplifiers(self, template: Dict[str, Any], region_names: List[str]) -> List[str]:
        scope = "、".join(region_names[:2]) or "关键区域"
        return [f"{scope}节点耦合增强", "高强度变量持续时间拉长", "跨区域传播路径增加", *template["dependencies"][:2]]

    def _buffers(self, template: Dict[str, Any], region_names: List[str]) -> List[str]:
        scope = "、".join(region_names[:2]) or "关键区域"
        return [f"{scope}提前监测", "资源预置与分流", "阈值触发的局部干预"]

    def _keyword_matches(self, text: str, keywords: List[str]) -> List[str]:
        normalized = str(text or "").lower()
        return self._unique([keyword for keyword in keywords if keyword.lower() in normalized])

    def _region_text(self, item: Dict[str, Any]) -> str:
        return self._join_text(
            item.get("name"),
            item.get("region_id"),
            item.get("region_type"),
            item.get("description"),
            item.get("land_use_class"),
            item.get("distance_band"),
            item.get("tags"),
            item.get("carriers"),
            item.get("ecology_assets"),
            item.get("industry_tags"),
            item.get("region_constraints"),
            item.get("exposure_channels"),
        )

    def _profile_text(self, item: Dict[str, Any]) -> str:
        return self._join_text(
            item.get("name"),
            item.get("username"),
            item.get("node_family"),
            item.get("role_type"),
            item.get("bio"),
            item.get("persona"),
            item.get("profession"),
            item.get("primary_region"),
            item.get("agent_type"),
            item.get("agent_subtype"),
            item.get("goals"),
            item.get("sensitivities"),
            item.get("capabilities"),
            item.get("constraints"),
            item.get("action_space"),
        )

    def _join_text(self, *values: Any) -> str:
        parts = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                parts.append(" ".join(str(item) for item in value))
            elif isinstance(value, dict):
                parts.append(" ".join(str(item) for item in value.values()))
            else:
                parts.append(str(value))
        return " ".join(parts)

    def _as_dict(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        if hasattr(item, "to_dict"):
            return item.to_dict()
        if hasattr(item, "__dict__"):
            return dict(item.__dict__)
        return {}

    def _coerce_score(self, value: Any, default: float = 0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if 0 <= number <= 1:
            number *= 100
        return max(0, min(100, number))

    def _unique(self, values: List[Any]) -> List[Any]:
        seen = set()
        result = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                value = re.sub(r"\s+", " ", value).strip()
                if not value:
                    continue
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result
