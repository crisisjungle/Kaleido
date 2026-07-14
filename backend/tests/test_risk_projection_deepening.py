import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.risk_projection import project_legacy_risk_objects


class RiskProjectionDeepeningTest(unittest.TestCase):
    """Prove the evolving runtime signals (runtime_tension, tension_trace,
    turning_point, status) are projected onto the legacy risk objects, plus a
    clearly-derived uncertainty band. All deterministic, no LLM/network."""

    def _definitions(self):
        return [
            {
                "risk_id": "risk_water",
                "title": "Water ecology stress",
                "confidence_score": 0.4,
                "severity_score": 50,
                "turning_points": ["template turning point"],
            }
        ]

    def _bundle(self, **overrides):
        state = {
            "risk_id": "risk_water",
            "status": "elevated",
            "severity_score": 63.0,
            "confidence_score": 0.4,
            "runtime_tension": 63.0,
            "tension_trace": [50.0, 55.0, 63.0],
            "turning_point": True,
        }
        state.update(overrides)
        return {"round": 3, "primary_active_risk_id": "risk_water", "risk_states": [state]}

    def test_runtime_signals_projected_onto_legacy_object(self):
        objects = project_legacy_risk_objects(self._definitions(), self._bundle())
        obj = objects[0]
        # Evolving runtime signals are merged through verbatim.
        self.assertEqual(obj["runtime_tension"], 63.0)
        self.assertEqual(obj["tension_trace"], [50.0, 55.0, 63.0])
        self.assertEqual(obj["runtime_status"], "elevated")
        self.assertTrue(obj["turning_point"])
        self.assertTrue(obj["has_runtime_signal"])
        # Legacy status reflects the runtime status (existing behavior preserved).
        self.assertEqual(obj["status"], "elevated")
        # Backward compatibility: the original template plural key is untouched.
        self.assertEqual(obj["turning_points"], ["template turning point"])

    def test_uncertainty_band_is_derived_and_reflects_runtime(self):
        objects = project_legacy_risk_objects(self._definitions(), self._bundle())
        band = objects[0]["uncertainty_band"]
        self.assertTrue(band["derived"])
        self.assertIn("非实测值", band["label"])
        # Band is centered on the live runtime tension.
        self.assertEqual(band["center"], 63.0)
        # Width has a strictly positive epistemic + volatility contribution.
        self.assertGreater(band["half_width"], 0.0)
        self.assertGreater(band["volatility_half_width"], 0.0)  # trace spread = 13 -> 6.5
        self.assertEqual(band["volatility_half_width"], 6.5)
        # Lower confidence widens the epistemic half-width vs. a confident risk.
        self.assertGreater(band["epistemic_half_width"], 5.0)
        self.assertEqual(band["lower"], round(max(0.0, 63.0 - band["half_width"]), 1))
        self.assertEqual(band["upper"], round(min(100.0, 63.0 + band["half_width"]), 1))

    def test_low_confidence_band_wider_than_high_confidence(self):
        wide = project_legacy_risk_objects(
            self._definitions(), self._bundle(confidence_score=0.1)
        )[0]["uncertainty_band"]
        narrow = project_legacy_risk_objects(
            self._definitions(), self._bundle(confidence_score=0.95)
        )[0]["uncertainty_band"]
        self.assertGreater(wide["epistemic_half_width"], narrow["epistemic_half_width"])

    def test_no_runtime_bundle_is_backward_compatible(self):
        objects = project_legacy_risk_objects(self._definitions(), {})
        obj = objects[0]
        # Additive keys still present but signal-empty so callers can tell "no run".
        self.assertFalse(obj["has_runtime_signal"])
        self.assertIsNone(obj["runtime_tension"])
        self.assertEqual(obj["tension_trace"], [])
        self.assertIsNone(obj["runtime_status"])
        self.assertFalse(obj["turning_point"])
        # Uncertainty band still derived; center is None with no runtime tension.
        self.assertTrue(obj["uncertainty_band"]["derived"])
        self.assertIsNone(obj["uncertainty_band"]["center"])
        # Existing legacy keys preserved.
        self.assertEqual(obj["confidence_score"], 0.4)
        self.assertEqual(obj["turning_points"], ["template turning point"])


if __name__ == "__main__":
    unittest.main()
