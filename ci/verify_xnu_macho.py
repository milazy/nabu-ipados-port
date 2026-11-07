#!/usr/bin/env python3
"""Host-only structure check for a compiled ARM64 XNU Mach-O candidate.

A successful check is *not* evidence of hardware bootability, valid Apple
signatures, complete iPadOS or a safe-to-flash payload.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

CPU_ARM64 = 0x0100000C
MH_EXECUTE = 2
LC_SEGMENT_64 = 0x19

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    data = args.input.read_bytes()
    if not 1024 * 1024 < len(data) < 400 * 1024 * 1024:
        raise ValueError("Unexpected XNU candidate file size")
    base = 0
    size = len(data)
    if data[:4] == b"\xca\xfe\xba\xbe":   # FAT 32 big endian
        count = struct.unpack_from(">I", data, 4)[0]
        if not 1 <= count <= 16:
            raise ValueError("Invalid FAT Mach-O architecture count")
        arm = []
        for idx in range(count):
            cpu, subtype, offset, length, align = struct.unpack_from(">5I", data, 8+20*idx)
            if cpu == CPU_ARM64:
                arm.append((offset, length))
        if len(arm) != 1:
            raise ValueError("Expected exactly one ARM64 slice")
        base, size = arm[0]
        if base + size > len(data):
            raise ValueError("ARM64 FAT slice out of bounds")
    if data[base:base+4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Not a little-endian ARM64 Mach-O executable")
    _, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from(
        "<8I", data, base
    )
    if cpu != CPU_ARM64 or filetype != MH_EXECUTE:
        raise ValueError(f"Unexpected CPU or filetype: {cpu:#x}, {filetype:#x}")
    if not 1 <= ncmds <= 400 or not 0 < sizeofcmds < size-32:
        raise ValueError("Invalid Mach-O load command table")
    cursor, end = base+32, base+32+sizeofcmds
    if end > base+size:
        raise ValueError("Load command area exceeds ARM64 slice")
    segments = []
    for index in range(ncmds):
        if cursor+8 > end:
            raise ValueError(f"Truncated load command {index}")
        cmd, cmdsize = struct.unpack_from("<II", data, cursor)
        if cmdsize < 8 or cursor+cmdsize > end:
            raise ValueError(f"Invalid load command length {index}")
        if cmd == LC_SEGMENT_64:
            if cmdsize < 72:
                raise ValueError("Truncated segment_64")
            name = data[cursor+8:cursor+24].split(b"\0",1)[0].decode("ascii","replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q",data,cursor+24)
            if fileoff+filesize > size:
                raise ValueError(f"Segment {name} file range is out of bounds")
            segments.append({"name":name,"vmaddr":hex(vmaddr),"vmsize":vmsize})
        cursor += cmdsize
    if cursor != end or len(segments) < 2:
        raise ValueError("Invalid segment count / load commands")
    result = {
        "file": args.input.name, "bytes":len(data), "arm64_slice_bytes":size,
        "sha256":hashlib.sha256(data).hexdigest(), "cputype":hex(cpu),
        "filetype":"MH_EXECUTE", "load_commands":ncmds,
        "segments":segments, "hardware_boot_qualified":False,
        "signing_or_apfs_qualified":False, "flashed_to_tablet":False
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("ARM64_XNU_MACHO_STRUCTURE_OK",flush=True)
    print(json.dumps({k:result[k] for k in ("bytes","sha256","cputype","load_commands")}),flush=True)

if __name__ == "__main__":
    main()
