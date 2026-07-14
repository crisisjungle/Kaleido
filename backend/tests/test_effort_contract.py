import hashlib
import json
import unittest

from app.services.effort_contract import (
    EFFORT_PROFILE_VERSION,
    LEGACY_EFFORT_PROFILE_VERSION,
    EffortContractError,
    EffortLockedError,
    assert_effort_reference,
    assert_effort_snapshot_consistency,
    build_effort_snapshot,
    effort_content_hash,
    effort_label,
    effort_operation_limit,
    effort_stage_budget,
    map_limit_scale,
    normalize_effort_level,
    normalize_effort_snapshot,
)


PROFILE_FIELDS = (
    "effort_level",
    "effort_label",
    "profile_version",
    "budget_multiplier",
    "recommended_total_token_min",
    "recommended_total_token_max",
    "stage_budgets",
    "invariants",
    "compatibility",
)


class EffortContractTestCase(unittest.TestCase):
    def test_default_and_aliases(self):
        self.assertEqual(normalize_effort_level(None), "high")
        self.assertEqual(normalize_effort_level("Extra High"), "extra_high")
        self.assertEqual(normalize_effort_level("extra-high"), "extra_high")
        self.assertEqual(effort_label("light"), "轻量")
        self.assertEqual(effort_label("high"), "深入")
        self.assertEqual(effort_label("extra_high"), "高强度")
        self.assertEqual(effort_label("ultra"), "极致")

    def test_snapshot_is_locked_and_profile_hash_is_stable(self):
        first = build_effort_snapshot("high")
        second = build_effort_snapshot("high")
        self.assertNotEqual(first["effort_snapshot_id"], second["effort_snapshot_id"])
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(first["content_hash"], effort_content_hash("high"))
        self.assertTrue(first["locked"])
        self.assertEqual(first["compatibility"]["search_mode"], "deep_search")
        self.assertEqual(first["profile_version"], EFFORT_PROFILE_VERSION)
        self.assertEqual(first["budget_multiplier"], 1.0)
        self.assertEqual(first["recommended_total_token_min"], 700_000)
        self.assertEqual(first["recommended_total_token_max"], 1_800_000)
        self.assertEqual(set(first["stage_budgets"]), {"step1", "step2", "step3", "step4"})

    def test_stage_budgets_compile_the_canonical_high_limits(self):
        snapshot = build_effort_snapshot("high")
        self.assertEqual(
            effort_operation_limit(snapshot, "step1", "planning_anchor_limit"), 40
        )
        self.assertEqual(
            effort_operation_limit(snapshot, "step2", "planned_agent_limit"), 120
        )
        self.assertEqual(
            effort_operation_limit(snapshot, "step3", "runtime_agent_total_limit"), 8
        )
        self.assertEqual(
            effort_operation_limit(snapshot, "step3", "runtime_agent_per_round_limit"), 2
        )
        self.assertEqual(effort_operation_limit(snapshot, "step4", "counterfactual_runs"), 1)
        self.assertEqual(map_limit_scale(snapshot), 1.0)
        self.assertEqual(effort_stage_budget(snapshot, "step3")["token_soft_limit"], 280_000)
        self.assertEqual(effort_stage_budget(snapshot, "step3")["token_hard_limit"], 720_000)
        self.assertEqual(snapshot["invariants"]["active_risk_limit"], 8)
        self.assertFalse(snapshot["invariants"]["broad_r4_scan_allowed"])

    def test_reference_rejects_snapshot_or_level_changes(self):
        snapshot = build_effort_snapshot("high", effort_snapshot_id="effort_workflow123")
        self.assertEqual(
            assert_effort_reference(
                snapshot,
                effort_snapshot_id="effort_workflow123",
                requested_level="High",
            )["effort_level"],
            "high",
        )
        with self.assertRaises(EffortLockedError):
            assert_effort_reference(snapshot, effort_snapshot_id="effort_other123")
        with self.assertRaises(EffortLockedError):
            assert_effort_reference(
                snapshot,
                effort_snapshot_id="effort_workflow123",
                requested_level="ultra",
            )

    def test_invalid_level_and_hash_are_rejected(self):
        with self.assertRaises(EffortContractError):
            build_effort_snapshot("unlimited")
        with self.assertRaises(EffortContractError):
            build_effort_snapshot("high", effort_snapshot_id="bad")

        tampered = build_effort_snapshot("high", effort_snapshot_id="effort_tampered123")
        tampered["content_hash"] = "0" * 64
        with self.assertRaises(EffortContractError):
            assert_effort_reference(tampered, effort_snapshot_id="effort_tampered123")

    def test_display_label_localization_keeps_existing_snapshot_readable(self):
        snapshot = build_effort_snapshot(
            "high",
            effort_snapshot_id="effort_legacylabel123",
        )
        snapshot["effort_label"] = "High"
        profile = {key: snapshot[key] for key in PROFILE_FIELDS}
        snapshot["content_hash"] = hashlib.sha256(
            json.dumps(
                profile,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        resolved = assert_effort_reference(
            snapshot,
            effort_snapshot_id="effort_legacylabel123",
        )
        self.assertEqual(resolved["effort_label"], "深入")
        self.assertEqual(resolved["content_hash"], effort_content_hash("high"))

        snapshot["stage_budgets"]["step2"]["operation_limits"]["planned_agent_limit"] = 99
        profile["stage_budgets"] = snapshot["stage_budgets"]
        snapshot["content_hash"] = hashlib.sha256(
            json.dumps(
                profile,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaises(EffortContractError):
            assert_effort_reference(
                snapshot,
                effort_snapshot_id="effort_legacylabel123",
            )

    def test_v1_snapshot_remains_readable_without_rewriting_its_contract(self):
        legacy_profile = {
            "effort_level": "high",
            "effort_label": "深入",
            "profile_version": LEGACY_EFFORT_PROFILE_VERSION,
            "stage_budgets": {
                "map_resolution_scale": 1.0,
                "mechanism_candidate_limit": 18,
                "alternative_chain_limit": 2,
                "spatial_detail_level": 3,
                "profile_detail_level": 3,
                "relationship_validation_hops": 3,
                "runtime_reasoning_depth": 3,
                "counterfactual_runs": 1,
                "report_review_passes": 2,
            },
            "compatibility": {
                "simulation_architecture": "llm_mechanism_v1",
                "search_mode": "deep_search",
            },
        }
        legacy_snapshot = {
            **legacy_profile,
            "effort_snapshot_id": "effort_frozenv1abc",
            "content_hash": hashlib.sha256(
                json.dumps(
                    legacy_profile,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "locked": True,
            "locked_at": "2026-07-13T12:00:00",
        }

        resolved = normalize_effort_snapshot(legacy_snapshot)

        self.assertEqual(resolved["profile_version"], LEGACY_EFFORT_PROFILE_VERSION)
        self.assertEqual(resolved["source"], "legacy_frozen")
        self.assertEqual(resolved["content_hash"], legacy_snapshot["content_hash"])
        self.assertEqual(map_limit_scale(resolved), 1.0)
        self.assertEqual(
            effort_stage_budget(resolved, "step2")["operation_limits"]["planned_agent_limit"],
            120,
        )

    def test_cross_stage_snapshot_consistency_checks_id_and_hash(self):
        snapshot = build_effort_snapshot("high", effort_snapshot_id="effort_shared123")
        self.assertEqual(
            assert_effort_snapshot_consistency(snapshot, dict(snapshot))["effort_snapshot_id"],
            "effort_shared123",
        )
        other = build_effort_snapshot("high", effort_snapshot_id="effort_other456")
        with self.assertRaises(EffortLockedError):
            assert_effort_snapshot_consistency(snapshot, other)


if __name__ == "__main__":
    unittest.main()
