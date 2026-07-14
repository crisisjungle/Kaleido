from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from .risk_candidate_extractor import MAX_ACTIVE_RISKS, RISK_CONTRACT_VERSION, RiskCandidateExtractor


@dataclass
class RiskEmergenceResult:
    risk_definitions: List[Dict[str, Any]]
    candidate_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    candidate_ledger: List[Dict[str, Any]] = field(default_factory=list)
    created_risk_ids: List[str] = field(default_factory=list)
    dormant_risk_ids: List[str] = field(default_factory=list)


class RiskEmergenceDetector:
    """Promote persistent runtime-only mechanism paths into read-only V2 risks."""

    def detect(self, **kwargs: Any) -> RiskEmergenceResult:
        definitions = [dict(item) for item in (kwargs.get("existing_definitions") or []) if isinstance(item, dict)]
        round_num = int(kwargs.get("current_round") or 0)
        previous_bundle = kwargs.get("previous_runtime_bundle") or {}
        previous_candidates = {
            str(key): dict(value)
            for key, value in (previous_bundle.get("emergence_candidates") or {}).items()
            if isinstance(value, dict)
        }
        extraction = RiskCandidateExtractor().extract(
            risk_contract_version=RISK_CONTRACT_VERSION,
            injected_variables=kwargs.get("active_variables") or [],
            regions=kwargs.get("regions") or [],
            subregions=kwargs.get("subregions") or [],
            profiles=kwargs.get("profiles") or [],
            transport_edges=kwargs.get("transport_edges") or [],
            agent_relationships=kwargs.get("agent_relationships") or [],
            mechanism_graph={},
            validated_relation_graph={},
            simulation_requirement=kwargs.get("simulation_requirement") or "",
            created_round=round_num,
            candidate_scan_limit=240,
        )
        existing_signatures = {str(item.get("source_signature") or "") for item in definitions}
        runtime_candidates = [
            item
            for item in extraction.definitions
            if self._is_runtime_candidate(item)
            and str(item.get("source_signature") or "") not in existing_signatures
            and not self._duplicates_existing_path(item, definitions)
        ]

        next_candidates: Dict[str, Dict[str, Any]] = {}
        events: List[Dict[str, Any]] = []
        ledger = self._summarize_extraction_rejections(extraction.candidate_ledger)
        created: List[str] = []
        dormant: List[str] = []
        runtime_states = {
            str(item.get("risk_id") or ""): item
            for item in (previous_bundle.get("risk_states") or [])
            if isinstance(item, dict)
        }

        for candidate in runtime_candidates:
            signature = str(candidate.get("source_signature") or "")
            previous = previous_candidates.get(signature) or {}
            consecutive = int(previous.get("consecutive_rounds") or 0) + 1 if int(previous.get("last_round") or -2) == round_num - 1 else 1
            record = {
                "risk_id": candidate.get("risk_id"),
                "title": candidate.get("title"),
                "last_round": round_num,
                "consecutive_rounds": consecutive,
                "evidence_strength_score": candidate.get("evidence_strength_score"),
                "impact_score": candidate.get("impact_score"),
                "priority_score": candidate.get("priority_score"),
            }
            next_candidates[signature] = record
            immediate = (
                float(candidate.get("evidence_strength_score") or 0) >= 80
                and float(candidate.get("impact_score") or 0) >= 80
            )
            if consecutive < 2 and not immediate:
                ledger.append(self._ledger_item(candidate, "pending", "需连续两轮通过校验"))
                continue

            admitted, demoted_id = self._admit_candidate(candidate, definitions, runtime_states)
            if not admitted:
                ledger.append(self._ledger_item(candidate, "candidate_only", "活跃风险已达上限，且优先级不足以替换观察对象"))
                continue
            if demoted_id:
                dormant.append(demoted_id)
            candidate["created_round"] = round_num
            candidate["generation_mode"] = "runtime_emergent_deterministic"
            candidate["mode"] = "incident"
            candidate["runtime_status"] = "watch"
            definitions.append(candidate)
            created.append(str(candidate.get("risk_id") or ""))
            existing_signatures.add(signature)
            events.append({
                "event_id": f"risk_event_{candidate.get('risk_id')}_{round_num}_emerged",
                "risk_id": candidate.get("risk_id"),
                "round": round_num,
                "event_type": "risk_emerged",
                "summary": f"新风险对象出现：{candidate.get('title')}。",
                "source_ref": "runtime:mechanism_path",
                "immediate": immediate,
                "timestamp": datetime.now().isoformat(),
            })
            ledger.append(self._ledger_item(candidate, "emerged", "达到运行时涌现阈值"))

        for signature, previous in previous_candidates.items():
            if signature in next_candidates:
                continue
            if round_num - int(previous.get("last_round") or round_num) <= 2:
                next_candidates[signature] = previous

        return RiskEmergenceResult(
            risk_definitions=definitions,
            candidate_state=next_candidates,
            events=events,
            candidate_ledger=ledger,
            created_risk_ids=created,
            dormant_risk_ids=dormant,
        )

    def _admit_candidate(
        self,
        candidate: Dict[str, Any],
        definitions: List[Dict[str, Any]],
        runtime_states: Dict[str, Dict[str, Any]],
    ) -> tuple[bool, str]:
        active = [
            item
            for item in definitions
            if str(
                (runtime_states.get(str(item.get("risk_id") or "")) or {}).get("status")
                or item.get("lifecycle_status")
                or item.get("runtime_status")
                or "watch"
            ) not in {"dormant", "resolved"}
        ]
        if len(active) < MAX_ACTIVE_RISKS:
            return True, ""
        replaceable = []
        for item in active:
            risk_id = str(item.get("risk_id") or "")
            status = str((runtime_states.get(risk_id) or {}).get("status") or "watch")
            if status == "watch":
                replaceable.append(item)
        if not replaceable:
            return False, ""
        lowest = min(replaceable, key=lambda item: float(item.get("priority_score") or item.get("severity_score") or 0))
        lowest_score = float(lowest.get("priority_score") or lowest.get("severity_score") or 0)
        if float(candidate.get("priority_score") or 0) < lowest_score + 10:
            return False, ""
        lowest["lifecycle_status"] = "dormant"
        lowest["runtime_status"] = "dormant"
        return True, str(lowest.get("risk_id") or "")

    def _is_runtime_candidate(self, item: Dict[str, Any]) -> bool:
        statement = item.get("risk_statement") or {}
        if statement.get("trigger_variable_ids"):
            return True
        edge_ids = [str(value or "").lower() for value in (item.get("mechanism_edge_ids") or [])]
        return any("dynamic" in edge_id or "runtime" in edge_id for edge_id in edge_ids)

    def _target_key(self, item: Dict[str, Any]) -> str:
        statement = item.get("risk_statement") or {}
        receptor = str(statement.get("receptor_name") or "").strip().lower()
        family = str(item.get("primary_family") or item.get("risk_type") or "").strip().lower()
        return f"{family}::{receptor}" if receptor else ""

    def _duplicates_existing_path(self, candidate: Dict[str, Any], definitions: List[Dict[str, Any]]) -> bool:
        statement = candidate.get("risk_statement") or {}
        source_ids = set(statement.get("source_node_ids") or [])
        receptor_ids = set(statement.get("receptor_node_ids") or [])
        edge_ids = set(candidate.get("mechanism_edge_ids") or [])
        for existing in definitions:
            existing_statement = existing.get("risk_statement") or {}
            if source_ids != set(existing_statement.get("source_node_ids") or []):
                continue
            if receptor_ids != set(existing_statement.get("receptor_node_ids") or []):
                continue
            existing_edges = set(existing.get("mechanism_edge_ids") or [])
            overlap = len(edge_ids & existing_edges) / max(1, min(len(edge_ids), len(existing_edges)))
            if overlap >= 0.6:
                return True
        return False

    def _ledger_item(self, item: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
        return {
            "risk_id": item.get("risk_id"),
            "source_signature": item.get("source_signature"),
            "status": status,
            "reason": reason,
            "title": item.get("title"),
            "priority_score": item.get("priority_score"),
            "evidence_strength_score": item.get("evidence_strength_score"),
            "mechanism_edge_ids": item.get("mechanism_edge_ids") or [],
        }

    def _summarize_extraction_rejections(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in items or []:
            if not isinstance(item, dict) or item.get("status") != "rejected":
                continue
            reason = str(item.get("reason") or "候选未通过校验")
            record = grouped.setdefault(reason, {
                "status": "rejected",
                "reason": reason,
                "rejected_candidate_count": 0,
                "mechanism_edge_ids": [],
                "source": "runtime_candidate_extraction",
            })
            record["rejected_candidate_count"] += 1
            known_edges = set(record["mechanism_edge_ids"])
            for edge_id in item.get("mechanism_edge_ids") or []:
                edge_id = str(edge_id or "")
                if edge_id and edge_id not in known_edges and len(record["mechanism_edge_ids"]) < 12:
                    record["mechanism_edge_ids"].append(edge_id)
                    known_edges.add(edge_id)
        return list(grouped.values())
