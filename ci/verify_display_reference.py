#!/usr/bin/env python3
"""Reject final kernels whose display bindings target a different prelink layout.

Run on the unmodified compiled images, before an owner firmware digest patch.
This verifies static address compatibility; it does not prove hardware boot.
"""
import argparse
import hashlib
import json
from pathlib import Path

MODULES = {
    "com.apple.iokit.IOMobileGraphicsFamily": "f216f3ad806f811575926f2f5f7e69fa9d700af9cd2c37575463aa0bb3d7ee85",
    "com.apple.iokit.IOSurface": "1166365c0e6e11c31b82d8d5808e1ed69d3449a9086336bee18fea2375e10031",
}
ORIGINAL = "f7d1952c7a21633d212eccf288e77444fff0cc86976db5de292f6819c2ffa1b2"

def load(image):
    report = json.loads(image.with_suffix(".json").read_text())
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if report["candidate_sha256"] != digest:
        raise ValueError(f"Prelink report/image mismatch: {image}")
    if report["original_sha256"] != ORIGINAL or report["slide"] != -0x1360000:
        raise ValueError(f"Unexpected original kernelcache or slide: {image}")
    for module, expected in MODULES.items():
        if report["original_executable_sha256"].get(module) != expected:
            raise ValueError(f"Unqualified original component: {module}")
    return report

def verify(reference, candidate):
    before, after = load(reference), load(candidate)
    checked = {}
    for module in MODULES:
        a = {e["segment"]: (e["va"], e["size"]) for e in before["extents"] if e["module"] == module}
        b = {e["segment"]: (e["va"], e["size"]) for e in after["extents"] if e["module"] == module}
        if not a or a != b:
            raise ValueError(f"Final component layout differs from compiled display reference: {module}")
        checked[module] = {name: {"va": hex(va), "bytes": size} for name, (va, size) in a.items()}
    return {"status": "DISPLAY_REFERENCE_LAYOUT_PASS", "reference_sha256": before["candidate_sha256"],
            "candidate_sha256": after["candidate_sha256"], "modules": checked, "hardware_boot_proven": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.reference, args.candidate)
    content = json.dumps(result, indent=2) + "\n"
    if args.report:
        if args.report.exists():
            raise FileExistsError(args.report)
        args.report.write_text(content)
    print(content, end="")

if __name__ == "__main__":
    main()
