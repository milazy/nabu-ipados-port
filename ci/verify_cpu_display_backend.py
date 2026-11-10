#!/usr/bin/env python3
"""Verify the compiled nabu CPU presentation backend rather than vendor-only flags."""
import argparse,hashlib,json,struct
from pathlib import Path

MARKERS=(
    b"NativeLegacyDisplay",b"offline-legacy-pm",b"nabu-cpu-present",
    b"sheng-vsync",b"nabu-gpu-scanout",b"NABU DISPLAY gpu-blit handoff ready",
    b"nabu-keybag-notifications",b"nabu-aks-state",
    b"nabu-disable-watchdogd",b"nabu-skip-setup",
)
METHODS=("validateSwap","validateSwapLocked","kickSwapQueue","vsyncFired")
GLOBALS=("_nabu_graphics_start_after_root","_nabu_graphics_worker_stage","_native_mobile_graphics_load_status")

def verify(path):
    b=path.read_bytes()
    header=struct.unpack_from("<8I",b)
    if header[0]!=0xfeedfacf or header[1]!=0x100000c or header[3]!=2:
        raise ValueError("Expected ARM64 executable Mach-O")
    missing=[x.decode() for x in MARKERS if x not in b]
    if missing:
        raise ValueError("Compiled backend markers missing: "+", ".join(missing))
    cursor=32
    table=None
    segments=[]
    for _ in range(header[4]):
        cmd,size=struct.unpack_from("<II",b,cursor)
        if size<8 or cursor+size>32+header[5]:
            raise ValueError("Malformed load command")
        if cmd==2:
            if table is not None:
                raise ValueError("Duplicate symbol table")
            table=struct.unpack_from("<4I",b,cursor+8)
        elif cmd==0x19:
            va,vs,fo,fs,maximum,initial=struct.unpack_from("<4Q2I",b,cursor+24)
            segments.append((va,vs,initial))
        cursor+=size
    if table is None:
        raise ValueError("Defined-symbol verification requires LC_SYMTAB")
    off,count,strings,string_bytes=table
    if off+count*16>len(b) or strings+string_bytes>len(b):
        raise ValueError("Symbol table exceeds file")
    symbols={}
    for i in range(count):
        strx,kind,section,desc,value=struct.unpack_from("<IBBHQ",b,off+i*16)
        if kind&0xe0 or kind&0x0e!=0x0e or not section:
            continue
        if strx>=string_bytes:
            raise ValueError("Symbol name exceeds string table")
        end=b.index(0,strings+strx,strings+string_bytes)
        symbols[b[strings+strx:end].decode(errors="replace")]=value
    checked={}
    for name in GLOBALS:
        matches=[(s,v) for s,v in symbols.items() if s==name]
        if len(matches)!=1:
            raise ValueError("Required graphics definition missing: "+name)
        checked[name]=hex(matches[0][1])
    for method in METHODS:
        matches=[(s,v) for s,v in symbols.items() if "NativeLegacyDisplay" in s and method in s]
        executable=[(s,v) for s,v in matches if any(va<=v<va+size and prot&4 for va,size,prot in segments)]
        if not executable:
            raise ValueError("Required executable display method missing: "+method)
        checked[method]=[{"symbol":s,"va":hex(v)} for s,v in executable]
    return {"status":"NABU_CPU_DISPLAY_BACKEND_PASS","candidate_sha256":hashlib.sha256(b).hexdigest(),
            "bytes":len(b),"required_markers":{x.decode():b.count(x) for x in MARKERS},
            "defined_backend_symbols":checked,"hardware_boot_proven":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    result=verify(a.input)
    if a.report.exists():
        raise FileExistsError(a.report)
    a.report.write_text(json.dumps(result,indent=2)+"\n")
    print("NABU_CPU_DISPLAY_BACKEND_PASS",result["candidate_sha256"])

if __name__=="__main__":
    main()
