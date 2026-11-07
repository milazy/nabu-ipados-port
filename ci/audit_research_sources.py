#!/usr/bin/env python3
"""Reproducible source-only audit for Pad 5 references.

This process NEVER executes third-party source, downloads Apple code, builds a
flashing image or touches hardware. The clone/fetch step belongs to CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

PIN = Path(__file__).with_name("research_sources.lock.json")
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_REL = re.compile(r"^[a-zA-Z0-9_+./-]+$")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def audit(root: Path, lock_file: Path = PIN) -> dict:
    lock = json.loads(lock_file.read_text(encoding="utf8"))
    failures = []
    if lock.get("schema") != 1:
        failures.append("Unsupported source lock schema")
    sources = {}
    for ref in lock["sources"]:
        slug, expected = ref["slug"], ref["sha"]
        if not HEX_SHA.fullmatch(expected):
            failures.append(f"{slug}: invalid SHA pin")
            continue
        tree = root / slug
        outcome = {"expected_sha": expected, "role": ref["role"], "verified": False, "files": {}}
        sources[slug] = outcome
        if not (tree / ".git").exists():
            failures.append(f"{slug}: missing Git checkout")
            continue
        head = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
        outcome["actual_sha"] = head.stdout.strip() if head.returncode == 0 else None
        if outcome["actual_sha"] != expected:
            failures.append(f"{slug}: revision differs from pinned SHA")
            continue
        for name in ref["required"]:
            if not SAFE_REL.fullmatch(name) or ".." in Path(name).parts or name.startswith("/"):
                failures.append(f"{slug}: unsafe path in lockfile")
                continue
            file = tree / name
            if not file.exists() or file.is_symlink():
                failures.append(f"{slug}: expected input missing or linked: {name}")
                continue
            if file.is_dir():
                count = sum(1 for p in file.iterdir() if p.is_file())
                if count < 1:
                    failures.append(f"{slug}: source directory empty: {name}")
                outcome["files"][name] = {"kind": "directory", "immediate_files": count}
            else:
                outcome["files"][name] = {
                    "kind": "file", "sha256": digest(file), "bytes": file.stat().st_size}
        if len(outcome["files"]) == len(ref["required"]):
            outcome["verified"] = True

    nabu_display = root / "nabu" / "platform/NabuLegacyDisplayProbe.cpp"
    vsync_stub = refresh_stub = None
    if nabu_display.is_file():
        data = nabu_display.read_text(encoding="utf8")
        vsync_stub = bool(re.search(r"native_legacy_vsync_notify\s*\([^)]*\)\s*\{\s*\}", data))
        refresh_stub = bool(re.search(
            r"native_legacy_set_refresh_properties\s*\([^)]*\)\s*\{\s*return\s+false\s*;\s*\}",
            data))
    hakios_plist = root / "hakios" / "userland/mkhighrate.py"
    pro_reference = (
        hakios_plist.is_file()
        and "CADisableMinimumFrameDurationOnPhone" in hakios_plist.read_text(encoding="utf8"))

    return {
        "status": "PASS_SOURCE_ONLY" if not failures else "FAIL",
        "checks": sources,
        "errors": failures,
        "display_review": {
            "nabu_noop_vsync_found": vsync_stub,
            "nabu_noop_refresh_properties_found": refresh_stub,
            "hakios_highrate_plist_reference_exists": pro_reference,
            "qualified_as_real_120hz": False,
        },
        "not_a_kernel_build": True,
        "not_an_install_image": True,
        "no_flash_commands_executed": True,
        "apple_services_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--lock", type=Path, default=PIN)
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    result = audit(a.root, a.lock)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_SOURCE_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
