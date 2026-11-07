#!/usr/bin/env python3
"""Fail-closed validation for a timer-free, non-resetting post-MMU control.

Must differ from the original owner-root XNU in exactly the same three hook
sites and three unused code caves as the immediate-reset diagnostic; cave 3
must contain only WFE and a backwards branch, with no other new code.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from validate_instant_postmmu import parse,sha,SOURCE_SHA,CAVE_OFFSETS

HALT=(0xD503205F,0x17FFFFFF)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original",type=Path,required=True)
    p.add_argument("--instrumented",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    args=p.parse_args()
    before=args.original.read_bytes()
    after=args.instrumented.read_bytes()
    if sha(before)!=SOURCE_SHA or len(after)!=len(before):
        raise RuntimeError("Incorrect owner-root baseline kernel")
    entry,off,word,dest=parse(before)
    if parse(after)[0]!=entry:
        raise RuntimeError("Mach-O entry was altered")
    first=dest(entry)
    if first is None:
        raise RuntimeError("Unexpected first branch")
    matches=[]
    for pc in range(first,first+0x1400,4):
        try:
            if (word(pc)==0xD5181000 and word(pc+4)==0xD5033FDF
                and word(pc+0x20)==0xD2A00600 and word(pc+0x24)==0xD5181040):
                matches.append(pc)
        except RuntimeError:
            break
    if len(matches)!=1:
        raise RuntimeError("Expected a unique verified MMU sequence")
    mmu=matches[0]
    post=mmu+0x20
    cave=off(entry+0x138)
    if struct.unpack_from("<2I",after,cave)!=HALT:
        raise RuntimeError("Stage 3 is not pinned no-reset WFE loop")
    if any(after[cave+8:cave+0x60]):
        raise RuntimeError("Unexpected code in post-MMU control cave")
    cave_ranges=[]
    for delta in CAVE_OFFSETS:
        c=off(entry+delta)
        if any(before[c:c+0x60]):
            raise RuntimeError("Code cave is not empty in original")
        cave_ranges.append((c,c+0x60))
    allowed=[(off(entry),off(entry)+4),(off(mmu),off(mmu)+4),
             (off(post),off(post)+4),*cave_ranges]
    patched=bytearray(after)
    changes=[]
    for a,b in allowed:
        num=sum(x!=y for x,y in zip(before[a:b],after[a:b]))
        if not num:
            raise RuntimeError("Expected hook or cave missing")
        patched[a:b]=before[a:b]
        changes.append({"file_offset":a,"length":b-a,"changed_bytes":num})
    if bytes(patched)!=before:
        raise RuntimeError("Kernel changed outside six permitted regions")
    for pc in (entry,mmu,post):
        if struct.unpack_from("<I",after,off(pc))[0] >> 26 != 0b000101:
            raise RuntimeError("Unconditional hook branch missing")
    report={"original_sha256":sha(before),"control_sha256":sha(after),
      "kernel_size":len(after),"mmu_hook":hex(mmu),"post_mmu_hook":hex(post),
      "only_six_regions_modified":True,"post_mmu_halt_opcode":[hex(v) for v in HALT],
      "intentional_reset":False,"timer":False,"storage_writes":False,
      "tablet_boot_tested":False,"ipad_os_installed":False,"modified_regions":changes}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("POSTMMU_HALT_CONTROL_VALIDATION_PASSED")
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
