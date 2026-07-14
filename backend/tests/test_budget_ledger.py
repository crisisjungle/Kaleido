import pytest

from app.services.budget_ledger import (
    BudgetExceededError,
    BudgetLedger,
    BudgetLedgerError,
    BudgetReservationError,
)
from app.services.effort_contract import build_effort_snapshot


def _ledger(level: str = "high") -> BudgetLedger:
    return BudgetLedger(
        build_effort_snapshot(level, effort_snapshot_id=f"effort_{level}ledger123")
    )


def test_reserve_and_settle_with_provider_usage():
    ledger = _ledger()
    reservation = ledger.reserve(
        stage="step2",
        operation="agent_profile_generation",
        reserved_tokens=40_000,
        model_or_provider="openai/test-model",
    )

    entry = ledger.settle(
        reservation,
        status="succeeded",
        input_tokens=12_000,
        output_tokens=4_000,
        reasoning_tokens=8_000,
        duration_ms=1300,
        produced_artifact_refs=["agent_profile:a1", "agent_profile:a1"],
    )

    assert entry.charged_tokens == 24_000
    assert entry.usage_source == "provider"
    assert entry.produced_artifact_refs == ["agent_profile:a1"]
    assert ledger.stage_summary("step2")["charged_tokens"] == 24_000
    assert ledger.summary()["entry_count"] == 1
    assert ledger.active_reservations() == []


def test_missing_provider_usage_charges_the_full_reservation():
    ledger = _ledger("light")
    reservation = ledger.reserve(
        stage="step4",
        operation="report_review",
        reserved_tokens=10_000,
        model_or_provider="provider-without-usage",
    )

    entry = ledger.settle(
        reservation,
        status="succeeded",
        provider_usage_available=False,
    )

    assert entry.input_tokens == 0
    assert entry.output_tokens == 0
    assert entry.reasoning_tokens == 0
    assert entry.charged_tokens == 10_000
    assert entry.usage_source == "reservation"


def test_release_records_audit_entry_without_charging_tokens():
    ledger = _ledger()
    reservation = ledger.reserve(
        stage="step1",
        operation="map_refinement",
        reserved_tokens=5_000,
        model_or_provider="map-provider",
    )

    entry = ledger.release(reservation)

    assert entry.status == "cancelled"
    assert entry.charged_tokens == 0
    assert entry.usage_source == "released"
    assert ledger.stage_summary("step1")["remaining_calls"] == 31


def test_soft_limit_requires_degradation_but_hard_limit_blocks_before_call():
    ledger = _ledger("light")
    first = ledger.reserve(
        stage="step1",
        operation="initial_map_scan",
        reserved_tokens=12_000,
        model_or_provider="map-provider",
    )
    assert first.degradation_required is False
    ledger.settle(first, status="succeeded", input_tokens=12_000)

    second = ledger.reserve(
        stage="step1",
        operation="targeted_refinement",
        reserved_tokens=1_000,
        model_or_provider="map-provider",
    )
    assert second.degradation_required is True
    ledger.release(second)

    with pytest.raises(BudgetExceededError, match="token 硬上限"):
        ledger.reserve(
            stage="step1",
            operation="unbounded_scan",
            reserved_tokens=19_000,
            model_or_provider="map-provider",
        )


def test_concurrency_and_double_settlement_are_rejected():
    ledger = _ledger("light")
    reservation = ledger.reserve(
        stage="step2",
        operation="mechanism_search",
        reserved_tokens=1_000,
        model_or_provider="test-model",
    )
    with pytest.raises(BudgetExceededError, match="并发预算"):
        ledger.reserve(
            stage="step2",
            operation="second_search",
            reserved_tokens=1_000,
            model_or_provider="test-model",
        )

    ledger.release(reservation)
    with pytest.raises(BudgetReservationError, match="已经结算"):
        ledger.release(reservation)


def test_operation_limits_come_from_the_locked_effort_snapshot():
    ledger = _ledger("extra_high")

    assert ledger.operation_limit("step1", "planning_anchor_limit") == 80
    assert ledger.operation_limit("step2", "planned_agent_limit") == 250
    assert ledger.operation_limit("step3", "runtime_agent_total_limit") == 20
    assert ledger.operation_limit("step3", "runtime_agent_per_round_limit") == 4
    assert ledger.operation_limit("step4", "counterfactual_runs") == 3


def test_historical_entries_must_match_the_locked_effort_snapshot():
    source = _ledger("high")
    reservation = source.reserve(
        stage="step2",
        operation="agent_profile_generation",
        reserved_tokens=1_000,
        model_or_provider="test-model",
    )
    source.settle(reservation, status="succeeded", input_tokens=500)
    entries = source.entries()
    entries[0]["effort_snapshot_ref"]["effort_snapshot_id"] = "effort_other123456"

    target_snapshot = build_effort_snapshot(
        "high", effort_snapshot_id="effort_highledger123"
    )
    with pytest.raises(BudgetLedgerError, match="Effort 快照不一致"):
        BudgetLedger(target_snapshot, entries=entries)
