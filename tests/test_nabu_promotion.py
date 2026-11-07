#!/usr/bin/env python3
"""Host-only regression tests for 120 Hz qualification. No device or network."""
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "ci/qualify_nabu_promotion.py"
spec = importlib.util.spec_from_file_location("promotion_audit", SRC)
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)


def trace(hz=120, frames=150):
    gap = round(1_000_000_000 / hz)
    return {"device": "nabu", "panel_variant": "nabu_csot",
            "panel_id": "verified-physical-csot-panel-id", "mode_set_verified": True,
            "vsync_hw_source": True, "active_mode_hz": 120,
            "vblank_timestamps_ns": [n * gap for n in range(frames)]}


class NabuPromotionTests(unittest.TestCase):
    def test_csot_mode_formula(self):
        self.assertEqual(sum(promotion.CSOT_H), 1768)
        self.assertEqual(sum(promotion.CSOT_V), 2758)
        self.assertAlmostEqual(promotion.panel_clock_khz(120), 585137.28)
        self.assertAlmostEqual(promotion.panel_clock_khz(104), 507118.976)

    def test_120hz_vblank_trace(self):
        result = promotion.check_runtime(trace(120))
        self.assertTrue(result["qualified"])
        self.assertAlmostEqual(result["measurements"]["estimated_hz"], 120, places=2)

    def test_60hz_trace_cannot_claim_120hz(self):
        result = promotion.check_runtime(trace(60))
        self.assertFalse(result["qualified"])

    def test_no_physical_evidence_fails(self):
        self.assertFalse(promotion.check_runtime(None)["qualified"])
        self.assertFalse(promotion.check_runtime({})["qualified"])

    def test_wrong_panel_variant_fails(self):
        t = trace()
        t["panel_variant"] = "unknown_tianma"
        self.assertFalse(promotion.check_runtime(t)["qualified"])

    def test_bad_vblank_sequence_fails(self):
        t = trace()
        t["vblank_timestamps_ns"][72] = t["vblank_timestamps_ns"][71]
        self.assertFalse(promotion.check_runtime(t)["qualified"])

    def test_apple_pro_profile_is_proposed_not_applied(self):
        report = promotion.build_report(None, trace())
        self.assertEqual(report["apple_profiles"]["stable"]["product_type"], "iPad7,11")
        self.assertEqual(report["apple_profiles"]["promotion_candidate"]["product_type"], "iPad7,3")
        self.assertFalse(report["apple_profiles"]["identity_switched"])
        self.assertFalse(report["promotable_as_verified_120hz"])

    def test_display_source_stubs_fail(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/promotion.DISPLAY_SOURCE
            source.parent.mkdir(parents=True)
            source.write_text(
                'void native_legacy_vsync_notify(void *, uint64_t, uint64_t, uint64_t) {}\n'
                'bool native_legacy_set_refresh_properties(void *) { return false; }\n')
            status = promotion.check_source(Path(td))
            self.assertFalse(status["native_vsync_provider_present"])
            self.assertFalse(status["refresh_properties_provider_present"])
            self.assertFalse(promotion.build_report(Path(td), trace())["promotable_as_verified_120hz"])


if __name__ == "__main__":
    unittest.main()
