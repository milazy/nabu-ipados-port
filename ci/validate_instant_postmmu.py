#!/usr/bin/env python3
"""Validate the immediate after-MMU XNU reset probe, fail closed.

It may change only the entry, MMU and post-MMU branch instructions,
and the three reserved 96-byte code caves. Its post-MMU code must be
the exact immediate ARM64 PSCI SYSTEM_RESET sequence (no timebase).
"""
from pathlib import Path
import argparse, hashlib, struct, json

SOURCE_SHA="756c173f8c4482638c7ef0431455c986b356c4b9ce7e25e9802fe446b90bff56"
CAVE_OFFSETS=(0x78,0xd8,0x138)
PSCI_RESET=(0x52800120,0x72b08000,0xaa1f03e1,0xaa1f03e2,0xaa1f03e3,0xd4000003)

def sha(b):return hashlib.sha256(b).hexdigest()

def parse(b):
    if len(b)<32:raise RuntimeError("Truncated kernel")
    magic,cpu,sub,ft,n,sz,fl,r=struct.unpack_from("<8I",b)
    if (magic,cpu,ft)!=(0xfeedfacf,0x100000c,2):raise RuntimeError("Invalid ARM64 Mach-O")
    at=32; segments=[]; entry=None
    for _ in range(n):
        cmd,length=struct.unpack_from("<II",b,at)
        if length<8 or at+length>len(b):raise RuntimeError("Malformed Mach-O load command")
        if cmd==0x19:
            _,va,vlen,off,size=struct.unpack_from("<16sQQQQ",b,at+8)
            if size:segments.append((va,va+min(vlen,size),off))
        if cmd==5 and length==288:
            if entry is not None:raise RuntimeError("Multiple entry commands")
            entry=struct.unpack_from("<Q",b,at+272)[0]
        at+=length
    if entry is None:raise RuntimeError("No ARM64 entry command")
    def off(addr):
        for start,end,fo in segments:
            if start<=addr<end:return fo+addr-start
        raise RuntimeError("VA not file-backed: "+hex(addr))
    def word(addr):return struct.unpack_from("<I",b,off(addr))[0]
    def dest(pc):
        w=word(pc)
        if w>>26!=0b000101:return None
        delta=w&0x3ffffff
        if delta&(1<<25):delta-=1<<26
        return pc+delta*4
    return entry,off,word,dest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original",type=Path,required=True)
    p.add_argument("--instrumented",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    original=a.original.read_bytes()
    changed=a.instrumented.read_bytes()
    if sha(original)!=SOURCE_SHA or len(original)!=len(changed):
        raise RuntimeError("Original XNU kernel changed")
    entry,off,word,dest=parse(original)
    if parse(changed)[0]!=entry:raise RuntimeError("Mach-O entry point changed")
    first=dest(entry)
    if first is None:raise RuntimeError("Original entry did not branch to first CPU")
    matches=[]
    for pc in range(first,first+0x1400,4):
        try:
            if (word(pc)==0xd5181000 and word(pc+4)==0xd5033fdf
                and word(pc+0x20)==0xd2a00600 and word(pc+0x24)==0xd5181040):
                matches.append(pc)
        except RuntimeError:break
    if len(matches)!=1:raise RuntimeError("Unexpected MMU instruction sequence")
    mmu=matches[0];post=mmu+0x20
    code_cave=entry+0x138
    found=struct.unpack_from("<6I",changed,off(code_cave))
    if found!=PSCI_RESET:raise RuntimeError("Post-MMU reset instructions are not the pinned no-timer sequence")
    cave_ranges=[]
    for ofs in CAVE_OFFSETS:
        p=off(entry+ofs)
        if any(original[p:p+0x60]):raise RuntimeError("Reserved cave has other code")
        cave_ranges.append((p,p+0x60))
    regions=[(off(entry),off(entry)+4),(off(mmu),off(mmu)+4),
             (off(post),off(post)+4),*cave_ranges]
    mutable=bytearray(changed)
    region_evidence=[]
    for a0,a1 in regions:
        delta=sum(x!=y for x,y in zip(original[a0:a1],changed[a0:a1]))
        if not delta:raise RuntimeError("Required instrumentation region unchanged")
        mutable[a0:a1]=original[a0:a1]
        region_evidence.append({"offset":a0,"length":a1-a0,"changed_bytes":delta})
    if bytes(mutable)!=original:
        raise RuntimeError("Unexpected kernel changes outside approved probe locations")
    for addr in (entry,mmu,post):
        w=struct.unpack_from("<I",changed,off(addr))[0]
        if w>>26!=0b000101:raise RuntimeError("Expected unconditional branch hook missing")
    report={
        "original_sha256":sha(original),"probe_sha256":sha(changed),"kernel_bytes":len(changed),
        "kernel_entry":hex(entry),"mmu_write_address":hex(mmu),
        "post_mmu_hook_address":hex(post),
        "post_mmu_code_cave":hex(code_cave),
        "post_mmu_immediate_psci_reset":True,
        "timer_used":False,"reset_delay_seconds":0,
        "only_six_approved_regions_modified":True,"modified_regions":region_evidence,
        "hardware_boot_qualified":False,"ipad_os_installed":False,"tablet_writes":False
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("INSTANT_POST_MMU_VALIDATION_PASSED",flush=True)
    print(json.dumps(report,indent=2),flush=True)

if __name__=="__main__":main()
