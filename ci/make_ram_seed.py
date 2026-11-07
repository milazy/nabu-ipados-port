#!/usr/bin/env python3
"""Host-only, empty APFS RAM Data seed for Xiaomi nabu experimental UniXNU.

Uses the distro's real mkapfs. Verifies NXSB/APSB and UUIDs from disk bytes
instead of depending on apfsutil (not packaged in Ubuntu 24.04).
This is NOT a provisioned iPadOS Data volume and does not access the tablet.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import uuid

CONTAINER_UUID = uuid.UUID("0A5EED00-0000-4000-8000-000000000000")
VOLUME_UUID = uuid.UUID("0A5EED00-0000-4000-8000-000000000001")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size-mib", type=int, default=32)
    args = parser.parse_args()
    if not 16 <= args.size_mib <= 256:
        parser.error("size must be 16–256 MiB")
    if not shutil.which("mkapfs"):
        parser.error("mkapfs (apfsprogs) is required")
    out = args.output.resolve()
    if out.exists():
        parser.error("refusing to overwrite existing output")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as f:
        f.truncate(args.size_mib * 1048576)
    subprocess.run(["mkapfs", "-L", "OwnerData", "-U", str(CONTAINER_UUID),
                    "-u", str(VOLUME_UUID), str(out)], check=True)

    h = hashlib.sha256()
    volume_hits = 0
    with out.open("rb") as f:
        first = f.read(4096)
        if first[32:36] != b"NXSB":
            raise RuntimeError("APFS container NXSB magic absent")
        block_size = struct.unpack_from("<I", first, 36)[0]
        if block_size != 4096:
            raise RuntimeError("Unexpected APFS block size")
        actual_container = uuid.UUID(bytes=first[72:88])
        if actual_container != CONTAINER_UUID:
            raise RuntimeError(f"APFS container UUID mismatch {actual_container}")
        f.seek(0)
        while block := f.read(4096):
            h.update(block)
            if len(block) != 4096:
                raise RuntimeError("APFS image is not block aligned")
            if block[32:36] == b"APSB":
                actual_volume = uuid.UUID(bytes=block[240:256])
                if actual_volume == VOLUME_UUID:
                    volume_hits += 1
    if volume_hits == 0:
        raise RuntimeError("APFS volume superblock UUID not found")
    if out.stat().st_size != args.size_mib * 1048576:
        raise RuntimeError("Image length mismatch")
    report = {
        "format": "empty APFS container for volatile RAM Data",
        "bytes": out.stat().st_size,
        "sha256": h.hexdigest(),
        "container_uuid": str(CONTAINER_UUID).upper(),
        "volume_uuid": str(VOLUME_UUID).upper(),
        "apfs_volume_superblock_hits": volume_hits,
        "block_bytes": 4096,
        "initial_var_files": 0,
        "guest_mutable": True,
        "production_storage_qualified": False,
        "tablet_connected_or_modified": False,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    sidecar = out.with_suffix(out.suffix + ".json")
    sidecar.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
