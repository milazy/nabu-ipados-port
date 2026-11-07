#!/usr/bin/env python3
"""Prove visual entry instrumentation changes ONLY two entry branch instructions
and two 96-byte zero-filled code caves in an existing owner-root XNU kernel.
No device IO. This is not evidence that the kernel boots on physical hardware.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ENTRY_OLDER_BUILD=0xfffffff00b9d0488
STAGE_CAVE_OFFSETS=(0x78,0xd8)

def digest(b):return hashlib.sha256(b).hexdigest()

def parse(b):
    if len(b)<32:raise ValueError("Truncated kernel")
    magic,cpu,subtype,filetype,ncmd,sz,flags,reserved=struct.unpack_from("<8I",b,0)
    if (magic,cpu,filetype)!=(0xfeedfacf,0x100000c,2):
        raise ValueError("Invalid ARM64 Mach-O file")
    at=32
    segments=[]
    entry=None
    for _ in range(ncmd):
        cmd,length=struct.unpack_from("<II",b,at)
        if length<8 or at+length>len(b):raise ValueError("Invalid load command")
        if cmd==0x19:
            name,va,vlen,offset,filesize=struct.unpack_from("<16sQQQQ",b,at+8)
            if filesize:
                segments.append((va,vlen,offset,filesize))
        if cmd==5 and length==288:
            if entry is not None: raise ValueError("Duplicate thread entry")
            entry=struct.unpack_from("<Q",b,at+272)[0]
        at+=length
    if entry is None:raise ValueError("No arm64 LC_UNIXTHREAD")
    def off(va):
        for start,size,offset,filesize in segments:
            if start<=va<start+min(size,filesize):return offset+(va-start)
        raise ValueError("Virtual address not backed by file: "+hex(va))
    def word(va):return struct.unpack_from("<I",b,off(va))[0]
    def target(va):
        ins=word(va)
        if ins>>26!=0b000101:return None
        displacement=ins&0x3ffffff
        if displacement&(1<<25):displacement-=1<<26
        return va+4*displacement
    return entry,off,word,target

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--original",type=Path,required=True)
    ap.add_argument("--instrumented",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    old=a.original.read_bytes()
    new=a.instrumented.read_bytes()
    if len(new)!=len(old) or digest(old)!="756c173f8c4482638c7ef0431455c986b356c4b9ce7e25e9802fe446b90bff56":
        raise RuntimeError("Owner-root kernel identity or byte count changed")
    oldpc,off,word,target=parse(old)
    newpc,newoff,_,_=parse(new)
    if oldpc!=newpc:raise RuntimeError("Mach-O entry point was changed")
    first=target(oldpc)
    if first is None:raise RuntimeError("Original kernel entry is not a branch")
    matches=[]
    for site in range(first,first+0x1400,4):
        try:
            if word(site)==0xD5181000 and word(site+4)==0xD5033FDF and word(site+0x20)==0xD2A00600 and word(site+0x24)==0xD5181040:
                matches.append(site)
        except ValueError:
            break
    if len(matches)!=1:raise RuntimeError("Not exactly one expected MMU handoff sequence")
    site=matches[0]
    caves=[oldpc+x for x in STAGE_CAVE_OFFSETS]
    regions=[(off(oldpc),off(oldpc)+4),(off(site),off(site)+4)]
    for cave in caves:
        p=off(cave)
        if any(old[p:p+0x60]):raise RuntimeError("Source probe padding not empty")
        regions.append((p,p+0x60))
    all_changes=[]
    mutable=bytearray(new)
    for start,end in regions:
        changed=sum(x!=y for x,y in zip(old[start:end],new[start:end]))
        if changed==0:raise RuntimeError("Expected probe region not changed")
        all_changes.append({"file_offset":start,"span":end-start,"changed_bytes":changed})
        mutable[start:end]=old[start:end]
    if bytes(mutable)!=old:
        raise RuntimeError("Unexpected changes outside two branch sites and two code caves")
    check_entry=struct.unpack_from("<I",new,off(oldpc))[0]
    check_mmu=struct.unpack_from("<I",new,off(site))[0]
    if check_entry>>26!=0b000101 or check_mmu>>26!=0b000101:
        raise RuntimeError("Instrumented hooks are not unconditional ARM64 branches")
    result={
      "original_sha256":digest(old),"probe_sha256":digest(new),
      "kernel_bytes":len(new),"entry":hex(oldpc),
      "start_first_cpu":hex(first),"mmu_enable_insn":hex(site),
      "changed_regions":all_changes,
      "all_other_kernel_bytes_unchanged":True,
      "no_reset":True,
      "boot_qualified":False,"ipadOS_installed":False,
      "physical_device_written":False
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,indent=2)+"\n")
    print("ENTRY_PROBE_PRECISE_BINARY_DIFF_PASS",flush=True)
    print(json.dumps(result,indent=2),flush=True)
if __name__=="__main__":main()
