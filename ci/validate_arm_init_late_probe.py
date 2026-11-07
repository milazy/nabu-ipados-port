#!/usr/bin/env python3
"""Fail-closed diff validator for owner-root XNU's late arm_init stage-4 probe.

Only the entry branch, MMU-stage branch, one uniquely identified BL instruction
inside _arm_init, and three empty 96-byte code caves may change.
This proves patch scope, not success of an on-device Apple OS boot.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ORIGINAL="756c173f8c4482638c7ef0431455c986b356c4b9ce7e25e9802fe446b90bff56"
TARGET_FUNCTION="_arm_init"
TARGET_CALLEE="_kernel_collection_adjust_mh_addrs"
CAVE_OFFSETS=(0x78,0xd8,0x198)
EXPECTED_CALL_VA=0xfffffff00bf0cc98

def sha(x): return hashlib.sha256(x).hexdigest()

def parse(x):
    if len(x)<32:raise RuntimeError("Mach-O too small")
    magic,cpu,sub,filetype,ncmd,size,flags,res=struct.unpack_from("<8I",x,0)
    if (magic,cpu,filetype)!=(0xfeedfacf,0x100000c,2):
        raise RuntimeError("Not source ARM64 kernel Mach-O")
    offset=32
    entry=None;segments=[];symcmd=None
    for _ in range(ncmd):
        cmd,length=struct.unpack_from("<II",x,offset)
        if length<8 or offset+length>len(x):raise RuntimeError("Invalid Mach-O command")
        if cmd==0x19:
            name,va,vsize,fileoff,filesize=struct.unpack_from("<16sQQQQ",x,offset+8)
            if filesize:segments.append((va,va+min(vsize,filesize),fileoff))
        if cmd==2:symcmd=struct.unpack_from("<IIII",x,offset+8)
        if cmd==5 and length==288:
            if entry is not None:raise RuntimeError("Duplicate LC_UNIXTHREAD")
            entry=struct.unpack_from("<Q",x,offset+272)[0]
        offset+=length
    if entry is None or symcmd is None:raise RuntimeError("Missing entry or symbol table")
    def tofile(addr):
        for first,last,fo in segments:
            if first<=addr<last:return fo+addr-first
        raise RuntimeError("Address not in file-backed segment: "+hex(addr))
    so,ns,st,ss=symcmd
    symbols={}
    byaddress={}
    for i in range(ns):
        nameoff,t,sect,desc,va=struct.unpack_from("<IBBHQ",x,so+i*16)
        if not nameoff or nameoff>=ss or not va:continue
        end=x.find(b"\0",st+nameoff,st+ss)
        if end<0:continue
        name=x[st+nameoff:end].decode(errors="replace")
        if name:
            symbols.setdefault(name,va)
            byaddress.setdefault(va,name)
    return entry,tofile,symbols,byaddress

def branch_target(pc,w,opcode):
    if w>>26 != opcode:return None
    imm=w&0x3ffffff
    if imm&0x2000000:imm-=0x4000000
    return pc+4*imm

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--original",type=Path,required=True)
    ap.add_argument("--instrumented",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    old=a.original.read_bytes()
    new=a.instrumented.read_bytes()
    if sha(old)!=ORIGINAL or len(new)!=len(old):
        raise RuntimeError("Unrecognized owner-root input kernel")
    entry,off,symbols,addresses=parse(old)
    newentry,_,_,_=parse(new)
    if entry!=newentry:raise RuntimeError("Entry changed")
    def word(addr):return struct.unpack_from("<I",old,off(addr))[0]
    start=branch_target(entry,word(entry),0b000101)
    if start is None or start!=symbols.get("_start_first_cpu"):
        raise RuntimeError("First CPU branch pattern mismatch")
    mmu=[]
    for va in range(start,start+0x1400,4):
        try:
            if (word(va)==0xD5181000 and word(va+4)==0xD5033FDF and
                word(va+0x20)==0xD2A00600 and word(va+0x24)==0xD5181040):
                mmu.append(va)
        except RuntimeError:break
    if len(mmu)!=1:raise RuntimeError("Expected unique MMU setup sequence")
    names=sorted(x for x in addresses if x>symbols[TARGET_FUNCTION])
    if not names:raise RuntimeError("No function boundary after _arm_init")
    low=symbols[TARGET_FUNCTION]
    high=names[0]
    callee=symbols[TARGET_CALLEE]
    matches=[]
    for va in range(low,high,4):
        if branch_target(va,word(va),0b100101)==callee:
            matches.append(va)
    if len(matches)!=1 or matches[0]!=EXPECTED_CALL_VA:
        raise RuntimeError("Target BL is not unique or differs from pinned address")
    changed_regions=[(off(entry),off(entry)+4),(off(mmu[0]),off(mmu[0])+4),
                     (off(matches[0]),off(matches[0])+4)]
    for va in [entry+x for x in CAVE_OFFSETS]:
        o=off(va)
        if any(old[o:o+0x60]):raise RuntimeError("Code cave not entirely unused")
        changed_regions.append((o,o+0x60))
    mutable=bytearray(new)
    modifications=[]
    for a0,a1 in changed_regions:
        changes=sum(u!=v for u,v in zip(old[a0:a1],new[a0:a1]))
        if not changes:raise RuntimeError("Expected code change not present")
        modifications.append({"offset":a0,"size":a1-a0,"modified_bytes":changes})
        mutable[a0:a1]=old[a0:a1]
    if bytes(mutable)!=old:raise RuntimeError("Kernel modified outside six approved code regions")
    for va in (entry,mmu[0],matches[0]):
        instr=struct.unpack_from("<I",new,off(va))[0]
        if branch_target(va,instr,0b000101) is None:
            raise RuntimeError("Unexpected non-branch instruction in hook")
    report={
        "original_sha256":ORIGINAL,"instrumented_sha256":sha(new),
        "kernel_bytes":len(new),"entry_va":hex(entry),
        "mmu_enable_va":hex(mmu[0]),
        "late_function":TARGET_FUNCTION,"probe_after_call":TARGET_CALLEE,
        "target_call_va":hex(matches[0]),"callee_va":hex(callee),
        "precise_changed_regions":modifications,
        "only_six_approved_code_regions_modified":True,
        "reset_after_return_seconds":8,
        "boot_qualified":False,"ipadOS_installed":False,
        "android_userdata_modified":False,
    }
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n")
    print("ARM_INIT_LATE_BOOT_HOOK_DIFF_PASS")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
