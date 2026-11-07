#!/usr/bin/env python3
"""Review a Xiaomi Pad 5 iPadOS candidate WITHOUT EVER WRITING TO A DEVICE.

An audited *host package* is NOT a flash authorization. The script never calls
adb, fastboot, disk utilities or shell commands.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

TARGET = {"device": "nabu", "ios_build": "21H16",
          "apple_profile": "iPad7,11", "root_transport": "native_ufs"}
REQUIRED = ("kernel", "adt", "os_volume", "systemos_volume",
            "trustcache_os", "trustcache_systemos", "uefi_esp")
HEX = re.compile(r"^[0-9a-f]{64}$")
MIN_BYTES = {"kernel": 32_000_000, "adt": 1_024, "os_volume": 256_000_000,
             "systemos_volume": 32_000_000, "trustcache_os": 128,
             "trustcache_systemos": 128, "uefi_esp": 16_000_000}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def file_from_manifest(root: Path, value: dict) -> Path | None:
    name = value.get("path")
    if not isinstance(name, str) or not name or "\\" in name:
        return None
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or str(relative) == ".":
        return None
    item = root / relative
    if not item.resolve().is_relative_to(root.resolve()) or item.is_symlink():
        return None
    return item


def overlaps(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def audit(candidate: Path, backup_report: Path | None = None) -> dict:
    errs: list[str] = []
    checks: dict = {}
    if not candidate.is_file():
        return {"host_package_complete": False, "ready_to_flash": False,
                "errors": ["No candidate manifest was provided"]}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"host_package_complete": False, "ready_to_flash": False,
                "errors": [f"Cannot parse candidate manifest: {exc}"]}
    if data.get("schema") != 1:
        errs.append("Unsupported candidate manifest schema")
    if not isinstance(data.get("target"), dict):
        errs.append("Target definition must be a dictionary")
        data["target"] = {}
    if not isinstance(data.get("artifacts"), dict):
        errs.append("Artifacts must be a dictionary")
        data["artifacts"] = {}
    if not isinstance(data.get("storage"), dict):
        errs.append("Storage inventory must be a dictionary")
        data["storage"] = {}
    for name, expected in TARGET.items():
        if data.get("target", {}).get(name) != expected:
            errs.append(f"Target {name}: expected {expected!r}")
    if data.get("target", {}).get("native_120hz_qualified") is True:
        errs.append("Do not assert native 120Hz without independent physical telemetry")
    if data.get("target", {}).get("apple_store_qualified") is True:
        errs.append("Do not assert App Store without independent device login and download tests")
    root = candidate.resolve().parent
    artifacts = data.get("artifacts", {})
    for name in REQUIRED:
        item = artifacts.get(name)
        if not isinstance(item, dict):
            errs.append(f"Missing artifact declaration: {name}")
            continue
        file = file_from_manifest(root, item)
        if file is None or not file.is_file():
            errs.append(f"Missing/unsafe artifact path: {name}")
            continue
        expected = item.get("sha256")
        if not isinstance(expected, str) or not HEX.fullmatch(expected):
            errs.append(f"Missing SHA256: {name}")
            continue
        real = sha256(file)
        ok = real == expected
        checks[name] = {"sha256_valid": ok, "bytes": file.stat().st_size}
        if not ok:
            errs.append(f"Artifact hash mismatch: {name}")
        if file.stat().st_size < MIN_BYTES[name]:
            errs.append(f"Artifact implausibly small: {name}")
        if name == "kernel" and file.open("rb").read(4) != b"\xcf\xfa\xed\xfe":
            errs.append("Kernel does not have a Mach-O 64-bit little-endian header")
        if name == "uefi_esp":
            with file.open("rb") as fd:
                sector = fd.read(512)
            if len(sector) != 512 or sector[510:512] != b"\x55\xaa" or b"FAT32" not in sector:
                errs.append("EFI image is not a recognized FAT32 boot sector")
    storage = data.get("storage", {})
    if storage.get("block_size") != 4096:
        errs.append("Missing/incorrect 4K UFS sector size for owner device")
    partitions, allocations = storage.get("partitions"), storage.get("allocations")
    if not isinstance(partitions, list) or not isinstance(allocations, list) or not partitions or not allocations:
        errs.append("Full read-only partition map and proposed LBA allocations required")
    else:
        def extent(obj):
            start, length = obj.get("start_lba"), obj.get("sectors")
            if not isinstance(start, int) or isinstance(start, bool) or start < 0:
                raise ValueError("invalid start_lba")
            if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
                raise ValueError("invalid sectors")
            return start, start + length
        try:
            for a in allocations:
                ext = extent(a)
                if a.get("purpose") not in ("os", "systemos", "data", "esp"):
                    errs.append("Invalid allocation purpose")
                for p in partitions:
                    if overlaps(ext, extent(p)):
                        errs.append("Proposed allocation overlaps existing partition: " +
                                    str(p.get("name", "unknown")))
            for i, a in enumerate(allocations):
                for other in allocations[i+1:]:
                    if overlaps(extent(a), extent(other)):
                        errs.append("Proposed allocations overlap")
            for protected in ("boot", "super", "userdata", "cust", "rescue"):
                if not any(p.get("name") == protected for p in partitions):
                    errs.append(f"GPT does not describe protected partition {protected}")
        except (ValueError, TypeError, AttributeError):
            errs.append("Malformed GPT LBA ranges")
    if backup_report is None or not backup_report.is_file():
        errs.append("Verified external backup report is required")
    else:
        try:
            backup = json.loads(backup_report.read_text(encoding="utf8"))
            if (backup.get("result") != "PASS" or backup.get("files", 0) < 30000 or
                    backup.get("bytes", 0) < 37_000_000_000 or
                    "NABU_IPADOS_LAB" not in backup.get("destination", "")):
                errs.append("External copy not independently verified")
        except (ValueError, OSError, TypeError):
            errs.append("Backup report unreadable")
    return {
        "host_package_complete": not errs,
        "ready_to_flash": False,  # physical recovery, actual tested boot and consent are never machine-inferred
        "requires_owner_destructive_approval": True,
        "requires_real_device_boot_validation": True,
        "native_120hz_tested": False,
        "apple_account_tested": False,
        "artifacts": checks,
        "errors": errs,
        "note": "No flashing or partition writing functionality exists in this validator.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--external-backup-report", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--require-complete", action="store_true")
    args = p.parse_args()
    result = audit(args.manifest, args.external_backup_report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.require_complete and not result["host_package_complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
