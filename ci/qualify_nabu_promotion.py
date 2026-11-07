#!/usr/bin/env python3
"""Host-only, fail-closed 120 Hz + iPad Pro profile audit for Xiaomi Pad 5.

This is a qualification gate and mode reference, NOT a display driver,
an Apple identity spoof, an iPadOS installer, or an instruction to flash.
No device connections, writes, subprocesses, downloads or secrets.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path

DISPLAY_SOURCE = "platform/NabuLegacyDisplayProbe.cpp"
SOURCE_PIN = "54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9"
NABU_RESOLUTION = [1600, 2560]  # panel physical orientation; rotate for landscape
CSOT_H = (1600, 88, 40, 40)
CSOT_V = (2560, 26, 4, 168)
IOS_BASE = {"product_type": "iPad7,11", "board": "j171ap", "cpid": "0x8010",
            "bdid": "0x1c", "pro_motion": False, "status": "existing_kernel_inputs"}
IOS_PRO_CANDIDATE = {
    "product_type": "iPad7,3", "board": "j207ap", "cpid": "0x8011",
    "bdid": "0x04", "pro_motion": True,
    "status": "research_only_not_applied",
    "caution": "Different SoC, board, DeviceTree and IPSW kernelcache; "
               "cannot swap identity without verifying full BuildManifest inputs",
}


def panel_clock_khz(hz: float) -> float:
    """Reference timing from Linux nabu CSOT panel patch, not a DSI register write."""
    return math.prod((sum(CSOT_H), sum(CSOT_V))) * hz / 1000


def check_source(source_dir: Path | None) -> dict:
    result = {
        "tree_checked": False, "source_exists": False, "source_pin": SOURCE_PIN,
        "native_vsync_provider_present": False,
        "refresh_properties_provider_present": False,
        "reason": "No source checkout supplied",
    }
    if source_dir is None:
        return result
    source = source_dir / DISPLAY_SOURCE
    result["tree_checked"] = True
    result["source_exists"] = source.is_file()
    if not source.is_file():
        result["reason"] = f"Missing {DISPLAY_SOURCE}"
        return result
    data = source.read_text(encoding="utf-8")
    # A stub is not a functional frame synchronization backend.
    vsync_stub = bool(re.search(
        r"native_legacy_vsync_notify\s*\([^)]*\)\s*\{\s*\}", data))
    refresh_stub = bool(re.search(
        r"native_legacy_set_refresh_properties\s*\([^)]*\)\s*\{\s*return\s+false\s*;\s*\}",
        data))
    result["native_vsync_provider_present"] = (
        "native_legacy_vsync_notify" in data and not vsync_stub)
    result["refresh_properties_provider_present"] = (
        "native_legacy_set_refresh_properties" in data and not refresh_stub)
    result["reason"] = (
        "Display provider has no-op vsync / refresh-property stubs"
        if vsync_stub or refresh_stub
        else "Source has no known stubs; implementation still requires review"
    )
    return result


def check_runtime(telemetry: dict | None) -> dict:
    result = {
        "qualified": False,
        "reason": "No physical panel and vblank trace supplied",
        "measurements": {},
    }
    if telemetry is None:
        return result
    required = {
        "device": "nabu",
        "panel_variant": "nabu_csot",
        "mode_set_verified": True,
        "vsync_hw_source": True,
    }
    for key, expected in required.items():
        if telemetry.get(key) != expected:
            result["reason"] = f"Unverified {key}; expected {expected!r}"
            return result
    panel_id = telemetry.get("panel_id")
    if not isinstance(panel_id, str) or not panel_id.strip():
        result["reason"] = "Actual panel identification was not supplied"
        return result
    if telemetry.get("active_mode_hz") != 120:
        result["reason"] = "Actual device display mode is not 120 Hz"
        return result
    stamps = telemetry.get("vblank_timestamps_ns")
    if (not isinstance(stamps, list) or len(stamps) < 121
            or any(isinstance(t, bool) or not isinstance(t, int) for t in stamps)):
        result["reason"] = "Need at least 121 integer hardware vblank timestamps"
        return result
    gaps_ms = [(b-a)/1_000_000 for a,b in zip(stamps, stamps[1:])]
    if any(g <= 0 for g in gaps_ms):
        result["reason"] = "Non-monotonic or duplicate hardware vblank timestamps"
        return result
    gaps_sorted = sorted(gaps_ms)
    mid = statistics.median(gaps_ms)
    p95 = gaps_sorted[math.ceil(.95*len(gaps_sorted))-1]
    worst = gaps_sorted[-1]
    result["measurements"] = {
        "samples": len(gaps_ms),
        "median_interval_ms": round(mid, 4),
        "p95_interval_ms": round(p95, 4),
        "max_interval_ms": round(worst, 4),
        "estimated_hz": round(1000/mid, 3),
        "panel_id": panel_id,
    }
    # This is an intentionally conservative sustained refresh validation.
    result["qualified"] = 7.9 <= mid <= 8.8 and p95 < 9.5 and worst < 16.5
    result["reason"] = (
        "Physical 120Hz vblank intervals pass thresholds" if result["qualified"]
        else "Measured vblank intervals do not demonstrate sustained 120Hz")
    return result


def build_report(source_dir: Path | None, telemetry: dict | None) -> dict:
    source = check_source(source_dir)
    run = check_runtime(telemetry)
    source_ready = source["native_vsync_provider_present"] and source[
        "refresh_properties_provider_present"]
    ready = source_ready and run["qualified"]
    return {
        "device": "Xiaomi Pad 5 nabu",
        "target": {"physical_pixels": NABU_RESOLUTION, "target_hz": 120,
                   "safe_fallback_hz": 60, "frame_budget_ms": 1000/120},
        "source": source,
        "panel_reference": {
            "panel_variant": "nabu_csot_only",
            "h_total": sum(CSOT_H), "v_total": sum(CSOT_V),
            "clock_120_khz": round(panel_clock_khz(120), 3),
            "clock_104_khz": round(panel_clock_khz(104), 3),
            "warning": "Linux patch notes 104 Hz was preferred before an "
                       "experimental 120 Hz timing. Do not use CSOT clock on "
                       "another panel revision or blindly program DSI.",
        },
        "apple_profiles": {"stable": IOS_BASE, "promotion_candidate": IOS_PRO_CANDIDATE,
                           "identity_switched": False},
        "runtime": run,
        "promotable_as_verified_120hz": ready,
        "missing": [
            *([] if source_ready else ["Implement functional nabu IOKit refresh properties and vblank event backend"]),
            *([] if run["qualified"] else ["Hardware-mode and timestamp evidence from physical nabu CSOT panel"]),
            "Independent full IPSW 21H16 iPad7,3 BuildManifest and ADT integration required"
        ],
        "no_partition_writes": True, "no_device_flashes": True,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nabu-source", type=Path)
    p.add_argument("--telemetry", type=Path,
                   help="JSON of hardware mode + at least 121 real vblank timestamps")
    p.add_argument("--json", type=Path, help="Write host-only audit report")
    p.add_argument("--require-qualified", action="store_true",
                   help="Fail until a real 120 Hz provider and device trace pass")
    a = p.parse_args(argv)
    trace = json.loads(a.telemetry.read_text(encoding="utf-8")) if a.telemetry else None
    report = build_report(a.nabu_source, trace)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(a.require_qualified and not report["promotable_as_verified_120hz"])


if __name__ == "__main__":
    raise SystemExit(main())
