#!/usr/bin/env python3
"""Read-only integrity audit of saved boot inputs; does not establish Android bootability."""
import argparse,hashlib,json,struct
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();base=a.root/'backups/critical-baseline'
    m=json.loads((base/'manifest.json').read_text())
    if not m.get('completed') or a.report.exists():raise ValueError('Incomplete source manifest or existing output')
    files=[]
    for name in ('boot_a','boot_b','vendor_boot_a','vendor_boot_b','dtbo_a','dtbo_b','vbmeta_a','vbmeta_b'):
        info=m['files'][name];path=base/(name+'.img')
        actual=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
        if path.stat().st_size!=info['bytes'] or actual!=info['sha256']:raise ValueError('Saved input mismatch: '+name)
        with path.open('rb') as stream:head=stream.read(64)
        entry={'name':name,'bytes':path.stat().st_size,'sha256':actual,'manifest_matches':True}
        if name.startswith('boot_'):
            entry['android_boot_header']=head[:8]==b'ANDROID!'
            if entry['android_boot_header']:entry['header_version']=struct.unpack_from('<I',head,40)[0]
        elif name.startswith('vendor_boot_'):entry['android_vendor_boot_header']=head[:8]==b'VNDRBOOT'
        elif name.startswith('vbmeta_'):entry['avb_header']=head[:4]==b'AVB0'
        files.append(entry)
    result={'status':'SAVED_BOOT_INPUTS_HASH_PASS_ANDROID_BOOT_UNVERIFIED','files':files,
      'device_access_performed':False,'restoration_performed':False,'Android_boot_proven':False,
      'limits':['Current device partition hashes and actual slot/root/Data state remain unverified.','Do not flash xbl, abl, persist or a GPT from these host checks.']}
    a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for f in files:print(f['name'],'hash OK',f.get('android_boot_header',f.get('android_vendor_boot_header',f.get('avb_header',''))))
if __name__=='__main__':main()
