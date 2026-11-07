#!/usr/bin/env python3
"""Merge pinned UniXNU XNU patches with nabu-specific patches for bootstrap CI.

This only stages source patches in GitHub Actions. It never touches firmware,
bootloader partitions, Apple system volumes, signing keys or any device.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil

EXCLUDED_BOOTSTRAP = {
    # The nabu source preparer changes this optional probe patch; it overlaps
    # console changes in nabu-vc-text-scale and fails a real dry-run apply.
    "offline-component-load-probes.patch",
}
EXPECTED_SHA = {
    "local-availability.patch": "a051857d524f8836068fd2f1182ebe9e9d9ccf28b9560fb27ad634b0cb93270e",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--device", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--owner-root", action="store_true",
                    help="Require pinned second static trust-cache patch for OS+SystemOS")
    args = ap.parse_args()

    upstream = args.upstream.resolve(strict=True)
    device = args.device.resolve(strict=True)
    if not upstream.is_dir() or not device.is_dir():
        raise SystemExit("Expected separate XNU patch directories")
    if upstream == device:
        raise SystemExit("Source and destination must differ")
    manifest = {"profile": "nabu_bootstrap_defconfig",
                "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "upstream": str(upstream), "staged_directory": str(device),
                "ignored_optional_patches": sorted(EXCLUDED_BOOTSTRAP),
                "entries": [], "device_writes": False}

    originals = set()
    for source in sorted(device.glob("*.patch")):
        originals.add(source.name)
        manifest["entries"].append({"name":source.name, "origin":"nabu", "sha256":sha(source)})
    for source in sorted(upstream.glob("*.patch")):
        if source.name in EXCLUDED_BOOTSTRAP:
            continue
        if source.name in originals:
            # The nabu patch always wins over an upstream patch of same name.
            continue
        if source.name in EXPECTED_SHA and sha(source) != EXPECTED_SHA[source.name]:
            raise RuntimeError(f"Pinned upstream patch changed unexpectedly: {source.name}")
        destination = device / source.name
        if destination.exists():
            raise RuntimeError(f"Unexpected existing destination {destination}")
        shutil.copyfile(source, destination)
        manifest["entries"].append({
            "name":source.name, "origin":"pinned-upstream", "sha256":sha(destination)
        })
    manifest["entries"].sort(key=lambda item:item["name"])
    second_trust="nabu-master-second-trust-cache.patch"
    trust_names={x["name"] for x in manifest["entries"]}
    if args.owner_root:
        if second_trust not in trust_names:
            raise RuntimeError("Owner-root kernel would lack mandatory second static trust cache")
        selected=device / second_trust
        if sha(selected)!="22bdb693b2ce3c1176ee3aafb01ff2767874bf1192ae4f0ff8908269c59d54c3":
            raise RuntimeError("Owner-root trust patch not rebased to pinned Apple XNU")
    elif second_trust in trust_names:
        raise RuntimeError("Unexpected owner-root trust patch in bootstrap/readonly build")
    expected = {x["name"] for x in manifest["entries"]}
    if "local-availability.patch" not in expected or "kernel-sdk-root.patch" not in expected:
        raise RuntimeError("Missing essential XNU build compatibility patches")
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"BOOTSTRAP_PATCH_STACK_READY={len(expected)}",flush=True)
    print(f"MANIFEST={args.report}",flush=True)

if __name__ == "__main__":
    main()
