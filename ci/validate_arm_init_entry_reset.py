#!/usr/bin/env python3
"""Fail-closed SHA-pinned _arm_init entry reset experiment validator.

Only three explicit branch hooks and three previously-zero 96B code caves
may change. The stage-4 entry cave must contain an immediate PSCI reset,
without timer reads, storage access, or an embedded installer.
"""
import argparse, json, struct
from pathlib import Path
from validate_before_collection_probe import parse, sha, branch_target

ORIGINAL="756c173f8c4482638c7ef0431455c986b356c4b9ce7e25e9802fe446b90bff56"
ARM_INIT=0xfffffff00bf0c730
ARM_INIT_OPCODE=0xd10343ff
CAVES=(0x78, 0xd8, 0x198)
RESET=(0x52800120, 0x72b08000, 0xaa1f03e1, 0xaa1f03e2,
       0xaa1f03e3, 0xd4000003, 0xd503205f, 0x17ffffff)

def run():
    ap=argparse.ArgumentParser()
    ap.add_argument("--original",type=Path,required=True)
    ap.add_argument("--instrumented",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    old=a.original.read_bytes()
    new=a.instrumented.read_bytes()
    if sha(old)!=ORIGINAL or len(new)!=len(old):
        raise RuntimeError("Unrecognized original kernel, or file length changed")
    entry,off,symbols,_=parse(old)
    new_entry,_,_,_=parse(new)
    if entry!=new_entry or symbols.get("_arm_init")!=ARM_INIT:
        raise RuntimeError("Entry or _arm_init symbol mismatch")
    def origword(va): return struct.unpack_from("<I",old,off(va))[0]
    def newword(va): return struct.unpack_from("<I",new,off(va))[0]
    if origword(ARM_INIT)!=ARM_INIT_OPCODE:
        raise RuntimeError("Original _arm_init entry instruction mismatch")
    first=branch_target(entry,origword(entry),0b000101)
    if first!=symbols.get("_start_first_cpu"):
        raise RuntimeError("First CPU entry branch does not match symbol")
    matches=[]
    for va in range(first,first+0x1400,4):
        try:
            if (origword(va)==0xd5181000 and origword(va+4)==0xd5033fdf
               and origword(va+0x20)==0xd2a00600 and origword(va+0x24)==0xd5181040):
                matches.append(va)
        except RuntimeError:
            break
    if len(matches)!=1:
        raise RuntimeError("MMU setup signature missing or ambiguous")
    mmu=matches[0]
    sites=(entry,mmu,ARM_INIT)
    for va,delta in zip(sites,CAVES):
        if branch_target(va,newword(va),0b000101) != entry+delta:
            raise RuntimeError(f"Incorrect patched branch target at {va:#x}")
    cave4_off=off(entry+CAVES[2])
    actual=struct.unpack_from("<8I",new,cave4_off)
    if actual!=RESET:
        raise RuntimeError(f"Immediate PSCI reset cave opcode mismatch: {actual}")
    if any(new[cave4_off+32:cave4_off+96]):
        raise RuntimeError("Unexpected instructions in stage 4 after PSCI reset")
    regions=[]
    for va in sites:
        i=off(va);regions.append((i,i+4))
    for delta in CAVES:
        i=off(entry+delta)
        if any(old[i:i+96]):
            raise RuntimeError("Code cave is not empty in baseline")
        regions.append((i,i+96))
    mutable=bytearray(new)
    changes=[]
    for begin,end in regions:
        n=sum(a!=b for a,b in zip(old[begin:end],new[begin:end]))
        if n==0:
            raise RuntimeError("Required hook or cave unexpectedly unchanged")
        changes.append({"offset":begin,"size":end-begin,"changed_bytes":n})
        mutable[begin:end]=old[begin:end]
    if bytes(mutable)!=old:
        raise RuntimeError("Kernel changed outside exactly six permitted regions")
    report={"baseline_sha256":ORIGINAL,"probe_sha256":sha(new),
        "kernel_bytes":len(new),"entry":hex(entry),"mmu_hook":hex(mmu),
        "arm_init_entry":hex(ARM_INIT),"reset_at_arm_init_entry":True,
        "reset_delay_seconds":0,"only_six_approved_regions_modified":True,
        "PSCI_reset":True,"filesystem_writes":False,
        "physical_boot_qualified":False,"ipados_installed":False,
        "regions":changes}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("ARM_INIT_ENTRY_RESET_STRICT_VALIDATION_PASS")
    print(json.dumps(report,indent=2))

if __name__=="__main__": run()
