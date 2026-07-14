"""Append-only budget accounting for high-cost planning operations.

The ledger reserves capacity before a model or retrieval call starts, then
settles against provider usage. If usage is unavailable, the reservation is
charged in full so missing telemetry can never create unbounded free budget.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from app.services.effort_contract import (
    EFFORT_STAGES,
    EffortContractError,
    effort_operation_limit,
    effort_stage_budget,
    normalize_effort_snapshot,
)


class BudgetLedgerError(RuntimeError):
    """Base error for invalid budget-ledger operations."""


class BudgetExceededError(BudgetLedgerError):
    """Raised before an operation would exceed a hard budget boundary."""


class BudgetReservationError(BudgetLedgerError):
    """Raised for missing, duplicated, or invalid reservations."""


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    effort_snapshot_ref: Dict[str, str]
    stage: str
    round_number: Optional[int]
    operation: str
    model_or_provider: str
    reserved_tokens: int
    degradation_required: bool
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(asdict(self))


@dataclass(frozen=True)
class BudgetLedgerEntry:
    budget_entry_id: str
    reservation_id: str
    effort_snapshot_ref: Dict[str, str]
    stage: str
    round_number: Optional[int]
    operation: str
    model_or_provider: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    reserved_tokens: int
    charged_tokens: int
    usage_source: str
    duration_ms: int
    status: str
    produced_artifact_refs: List[str]
    degradation_applied: List[str]
    stop_reason: str
    hard_limit_exceeded: bool
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(asdict(self))


EntrySink = Callable[[Mapping[str, Any]], None]


class BudgetLedger:
    """Thread-safe reservation and settlement ledger for one Effort snapshot."""

    _SETTLED_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}

    def __init__(
        self,
        effort_snapshot: Mapping[str, Any],
        *,
        entries: Optional[Iterable[Mapping[str, Any]]] = None,
        entry_sink: Optional[EntrySink] = None,
    ) -> None:
        self._snapshot = normalize_effort_snapshot(effort_snapshot)
        self._snapshot_ref = {
            "effort_snapshot_id": str(self._snapshot["effort_snapshot_id"]),
            "content_hash": str(self._snapshot["content_hash"]),
            "effort_level": str(self._snapshot["effort_level"]),
            "profile_version": str(self._snapshot["profile_version"]),
        }
        self._entries: List[BudgetLedgerEntry] = []
        self._reservations: Dict[str, BudgetReservation] = {}
        self._entry_sink = entry_sink
        self._lock = RLock()
        for raw_entry in entries or []:
            entry = self._entry_from_mapping(raw_entry)
            self._validate_entry_snapshot(entry)
            self._entries.append(entry)

    @property
    def effort_snapshot_ref(self) -> Dict[str, str]:
        return dict(self._snapshot_ref)

    def reserve(
        self,
        *,
        stage: str,
        operation: str,
        reserved_tokens: int,
        model_or_provider: str,
        round_number: Optional[int] = None,
    ) -> BudgetReservation:
        normalized_stage = self._normalize_stage(stage)
        normalized_operation = str(operation or "").strip()
        if not normalized_operation:
            raise BudgetReservationError("预算预留必须声明操作名称")
        normalized_provider = str(model_or_provider or "").strip()
        if not normalized_provider:
            raise BudgetReservationError("预算预留必须声明模型或服务提供方")
        tokens = self._nonnegative_int(reserved_tokens, "预留 token")
        normalized_round = self._normalize_round(round_number)

        with self._lock:
            budget = effort_stage_budget(self._snapshot, normalized_stage)
            active = self._active_for_stage(normalized_stage)
            if len(active) >= int(budget["concurrency_limit"]):
                raise BudgetExceededError(
                    f"{normalized_stage} 并发预算已满，请等待现有操作结算"
                )
            initiated_calls = self._settled_call_count(normalized_stage) + len(active)
            if initiated_calls >= int(budget["call_limit"]):
                raise BudgetExceededError(f"{normalized_stage} 调用次数已达到硬上限")
            projected = (
                self._charged_tokens(normalized_stage)
                + sum(item.reserved_tokens for item in active)
                + tokens
            )
            if projected > int(budget["token_hard_limit"]):
                raise BudgetExceededError(
                    f"{normalized_stage} 预算不足，当前操作会超过 token 硬上限"
                )
            reservation = BudgetReservation(
                reservation_id=f"budget_res_{uuid.uuid4().hex[:16]}",
                effort_snapshot_ref=dict(self._snapshot_ref),
                stage=normalized_stage,
                round_number=normalized_round,
                operation=normalized_operation,
                model_or_provider=normalized_provider,
                reserved_tokens=tokens,
                degradation_required=projected > int(budget["token_soft_limit"]),
                created_at=datetime.now().isoformat(),
            )
            self._reservations[reservation.reservation_id] = reservation
            return reservation

    def settle(
        self,
        reservation: BudgetReservation | str,
        *,
        status: str,
        provider_usage_available: bool = True,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        reasoning_tokens: Optional[int] = None,
        duration_ms: int = 0,
        produced_artifact_refs: Optional[Iterable[str]] = None,
        degradation_applied: Optional[Iterable[str]] = None,
        stop_reason: str = "",
    ) -> BudgetLedgerEntry:
        reservation_id = self._reservation_id(reservation)
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in self._SETTLED_STATUSES:
            raise BudgetReservationError(f"不支持的预算结算状态: {status}")
        duration = self._nonnegative_int(duration_ms, "执行时长")

        with self._lock:
            active = self._reservations.get(reservation_id)
            if active is None:
                raise BudgetReservationError("预算预留不存在或已经结算")
            if provider_usage_available:
                used_input = self._nonnegative_int(input_tokens or 0, "输入 token")
                used_output = self._nonnegative_int(output_tokens or 0, "输出 token")
                used_reasoning = self._nonnegative_int(reasoning_tokens or 0, "推理 token")
                charged_tokens = used_input + used_output + used_reasoning
                usage_source = "provider"
            else:
                used_input = 0
                used_output = 0
                used_reasoning = 0
                charged_tokens = active.reserved_tokens
                usage_source = "reservation"

            budget = effort_stage_budget(self._snapshot, active.stage)
            projected_spend = self._charged_tokens(active.stage) + charged_tokens
            hard_limit_exceeded = projected_spend > int(budget["token_hard_limit"])
            entry = BudgetLedgerEntry(
                budget_entry_id=f"budget_entry_{uuid.uuid4().hex[:16]}",
                reservation_id=active.reservation_id,
                effort_snapshot_ref=dict(self._snapshot_ref),
                stage=active.stage,
                round_number=active.round_number,
                operation=active.operation,
                model_or_provider=active.model_or_provider,
                input_tokens=used_input,
                output_tokens=used_output,
                reasoning_tokens=used_reasoning,
                reserved_tokens=active.reserved_tokens,
                charged_tokens=charged_tokens,
                usage_source=usage_source,
                duration_ms=duration,
                status=normalized_status,
                produced_artifact_refs=self._normalized_strings(produced_artifact_refs),
                degradation_applied=self._normalized_strings(degradation_applied),
                stop_reason=str(stop_reason or "").strip(),
                hard_limit_exceeded=hard_limit_exceeded,
                created_at=datetime.now().isoformat(),
            )
            del self._reservations[reservation_id]
            self._append(entry)
            return entry

    def release(
        self,
        reservation: BudgetReservation | str,
        *,
        stop_reason: str = "调用未开始，已释放预留预算",
    ) -> BudgetLedgerEntry:
        reservation_id = self._reservation_id(reservation)
        with self._lock:
            active = self._reservations.get(reservation_id)
            if active is None:
                raise BudgetReservationError("预算预留不存在或已经结算")
            entry = BudgetLedgerEntry(
                budget_entry_id=f"budget_entry_{uuid.uuid4().hex[:16]}",
                reservation_id=active.reservation_id,
                effort_snapshot_ref=dict(self._snapshot_ref),
                stage=active.stage,
                round_number=active.round_number,
                operation=active.operation,
                model_or_provider=active.model_or_provider,
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                reserved_tokens=active.reserved_tokens,
                charged_tokens=0,
                usage_source="released",
                duration_ms=0,
                status="cancelled",
                produced_artifact_refs=[],
                degradation_applied=[],
                stop_reason=str(stop_reason or "").strip(),
                hard_limit_exceeded=False,
                created_at=datetime.now().isoformat(),
            )
            del self._reservations[reservation_id]
            self._append(entry)
            return entry

    def operation_limit(self, stage: str, operation: str) -> Any:
        return effort_operation_limit(self._snapshot, stage, operation)

    def entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [entry.to_dict() for entry in self._entries]

    def active_reservations(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in self._reservations.values()]

    def stage_summary(self, stage: str) -> Dict[str, Any]:
        normalized_stage = self._normalize_stage(stage)
        with self._lock:
            budget = effort_stage_budget(self._snapshot, normalized_stage)
            charged = self._charged_tokens(normalized_stage)
            active = self._active_for_stage(normalized_stage)
            reserved = sum(item.reserved_tokens for item in active)
            initiated = self._settled_call_count(normalized_stage) + len(active)
            return {
                "stage": normalized_stage,
                "token_soft_limit": int(budget["token_soft_limit"]),
                "token_hard_limit": int(budget["token_hard_limit"]),
                "charged_tokens": charged,
                "active_reserved_tokens": reserved,
                "remaining_hard_tokens": max(
                    0, int(budget["token_hard_limit"]) - charged - reserved
                ),
                "soft_limit_reached": charged + reserved >= int(budget["token_soft_limit"]),
                "hard_limit_reached": charged + reserved >= int(budget["token_hard_limit"]),
                "call_limit": int(budget["call_limit"]),
                "initiated_calls": initiated,
                "remaining_calls": max(0, int(budget["call_limit"]) - initiated),
                "concurrency_limit": int(budget["concurrency_limit"]),
                "active_calls": len(active),
                "degradation_order": list(budget.get("degradation_order") or []),
            }

    def summary(self) -> Dict[str, Any]:
        stages = {stage: self.stage_summary(stage) for stage in EFFORT_STAGES}
        return {
            "effort_snapshot_ref": dict(self._snapshot_ref),
            "stages": stages,
            "charged_tokens": sum(item["charged_tokens"] for item in stages.values()),
            "active_reserved_tokens": sum(
                item["active_reserved_tokens"] for item in stages.values()
            ),
            "entry_count": len(self._entries),
            "active_reservation_count": len(self._reservations),
        }

    def _append(self, entry: BudgetLedgerEntry) -> None:
        self._entries.append(entry)
        if self._entry_sink is not None:
            self._entry_sink(entry.to_dict())

    def _charged_tokens(self, stage: str) -> int:
        return sum(entry.charged_tokens for entry in self._entries if entry.stage == stage)

    def _settled_call_count(self, stage: str) -> int:
        return sum(1 for entry in self._entries if entry.stage == stage)

    def _active_for_stage(self, stage: str) -> List[BudgetReservation]:
        return [item for item in self._reservations.values() if item.stage == stage]

    def _validate_entry_snapshot(self, entry: BudgetLedgerEntry) -> None:
        for key, expected in self._snapshot_ref.items():
            actual = str(entry.effort_snapshot_ref.get(key) or "")
            if actual != expected:
                raise BudgetLedgerError(
                    f"历史预算条目与当前 Effort 快照不一致: {key}"
                )

    @staticmethod
    def _reservation_id(reservation: BudgetReservation | str) -> str:
        if isinstance(reservation, BudgetReservation):
            return reservation.reservation_id
        value = str(reservation or "").strip()
        if not value:
            raise BudgetReservationError("缺少预算预留标识")
        return value

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        normalized = str(stage or "").strip().lower()
        if normalized not in EFFORT_STAGES:
            raise BudgetReservationError(f"不支持的预算阶段: {stage}")
        return normalized

    @staticmethod
    def _normalize_round(round_number: Optional[int]) -> Optional[int]:
        if round_number is None:
            return None
        value = BudgetLedger._nonnegative_int(round_number, "轮次")
        return value

    @staticmethod
    def _nonnegative_int(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise BudgetReservationError(f"{label}必须是非负整数")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise BudgetReservationError(f"{label}必须是非负整数") from exc
        if normalized < 0 or normalized != value:
            raise BudgetReservationError(f"{label}必须是非负整数")
        return normalized

    @staticmethod
    def _normalized_strings(values: Optional[Iterable[str]]) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values or []:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    @staticmethod
    def _entry_from_mapping(raw: Mapping[str, Any]) -> BudgetLedgerEntry:
        try:
            entry = BudgetLedgerEntry(
                budget_entry_id=str(raw["budget_entry_id"]),
                reservation_id=str(raw["reservation_id"]),
                effort_snapshot_ref=dict(raw["effort_snapshot_ref"]),
                stage=str(raw["stage"]),
                round_number=raw.get("round_number"),
                operation=str(raw["operation"]),
                model_or_provider=str(raw["model_or_provider"]),
                input_tokens=int(raw.get("input_tokens") or 0),
                output_tokens=int(raw.get("output_tokens") or 0),
                reasoning_tokens=int(raw.get("reasoning_tokens") or 0),
                reserved_tokens=int(raw.get("reserved_tokens") or 0),
                charged_tokens=int(raw.get("charged_tokens") or 0),
                usage_source=str(raw.get("usage_source") or "provider"),
                duration_ms=int(raw.get("duration_ms") or 0),
                status=str(raw["status"]),
                produced_artifact_refs=list(raw.get("produced_artifact_refs") or []),
                degradation_applied=list(raw.get("degradation_applied") or []),
                stop_reason=str(raw.get("stop_reason") or ""),
                hard_limit_exceeded=bool(raw.get("hard_limit_exceeded", False)),
                created_at=str(raw["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BudgetLedgerError("无法读取历史预算账本条目") from exc
        if entry.stage not in EFFORT_STAGES:
            raise BudgetLedgerError(f"历史预算条目包含未知阶段: {entry.stage}")
        required_snapshot_ref_fields = {
            "effort_snapshot_id",
            "content_hash",
            "effort_level",
            "profile_version",
        }
        if not required_snapshot_ref_fields.issubset(entry.effort_snapshot_ref):
            raise BudgetLedgerError("历史预算条目的快照引用不完整")
        return entry


__all__ = [
    "BudgetExceededError",
    "BudgetLedger",
    "BudgetLedgerEntry",
    "BudgetLedgerError",
    "BudgetReservation",
    "BudgetReservationError",
]
