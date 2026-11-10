#!/usr/bin/env python3
"""Change only nabu's reserved DarwinBoot window from 1 GiB to 2 GiB."""
import argparse,hashlib,json,struct
from pathlib import Path

def require(ok,message):
    if not ok:raise ValueError(message)
def decode_properties(data):
    cursor=0;properties={};nodes=0
    def node(parent,depth):
        nonlocal cursor,nodes
        require(depth<=32 and cursor+8<=len(data),'ADT node bounds')
        count,children=struct.unpack_from('<II',data,cursor);cursor+=8;nodes+=1
        require(nodes<=4096 and count<=4096 and children<=4096,'ADT count limits')
        values=[];names=set();name=None
        for _ in range(count):
            require(cursor+36<=len(data),'ADT property header bounds')
            raw=data[cursor:cursor+32];size=struct.unpack_from('<I',data,cursor+32)[0]&0x7fffffff
            require(b'\0' in raw,'Unterminated ADT name')
            key=raw.split(b'\0',1)[0].decode('ascii');cursor+=36
            require(key not in names and cursor+((size+3)&~3)<=len(data),'Duplicate or truncated ADT property')
            names.add(key);value=data[cursor:cursor+size];values.append((key,value,cursor))
            if key=='name':name=value.rstrip(b'\0').decode('ascii')
            cursor+=(size+3)&~3
        require(name is not None and '/' not in name.strip('/'),'ADT node identity')
        path='' if depth==0 else parent+'/'+name
        for key,value,offset in values:properties[(path or '/',key)]=(value,offset)
        for _ in range(children):node(path,depth+1)
    node('',0);require(cursor==len(data),'ADT trailing bytes')
    return properties

def prepare(source,output,report):
    data=source.read_bytes();expected='658e38300dfd05e9a8c03e4c44790192c313949b627c72dfdb9144c7c889f12c'
    require(hashlib.sha256(data).hexdigest()==expected,'Expected the installed nabu ADT exactly')
    require(not output.exists() and not report.exists(),'Output already exists')
    before=decode_properties(data);key=('/chosen','darwinboot-memory-size')
    value,offset=before[key]
    require(value==struct.pack('<Q',0x40000000),'Previous allocation window is not 1 GiB')
    dram=before[('/chosen','dram-size')][0]
    require(len(dram)==8 and struct.unpack('<Q',dram)[0]>=0x80000000,'ADT DRAM contract smaller than requested window')
    after=bytearray(data);struct.pack_into('<Q',after,offset,0x80000000);after=bytes(after)
    decoded=decode_properties(after);require(set(decoded)==set(before),'ADT topology changed')
    for item,(old,old_offset) in before.items():
        new,new_offset=decoded[item]
        require(new_offset==old_offset and new==(struct.pack('<Q',0x80000000) if item==key else old),'Unexpected ADT property change')
    changed=[i for i,(a,b) in enumerate(zip(data,after)) if a!=b]
    require(len(data)==len(after) and changed==[offset+3],'Expected only the 0x40 to 0x80 window-size byte')
    output.write_bytes(after)
    result={'status':'NABU_RESERVED_MEMORY_WINDOW_HOST_PASS','old_sha256':expected,'new_sha256':hashlib.sha256(after).hexdigest(),
      'bytes':len(after),'property':'/chosen/darwinboot-memory-size','old_bytes':0x40000000,'new_bytes':0x80000000,
      'changed_file_offsets':changed,'all_other_properties_identical':True,'output_path':str(output.resolve()),
      'firmware_allocation_proven':False,'boot_proven':False,
      'allocation_rule':'Existing DarwinBoot must successfully reserve one real conventional-memory run with AllocatePages; no fabricated RAM or allocation bypass.'}
    report.write_text(json.dumps(result,indent=2)+'\n');return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('input','output','report'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();result=prepare(a.input,a.output,a.report)
    print(result['status'],result['new_sha256'])
if __name__=='__main__':main()
