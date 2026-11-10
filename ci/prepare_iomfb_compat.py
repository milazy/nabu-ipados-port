#!/usr/bin/env python3
"""Prepare a source-bound IOMFB compatibility kernel from run 42822755938."""
import argparse,hashlib,json
from pathlib import Path
from audit_compositor_transport import audit,need
from verify_cpu_display_backend import verify

EXPECTED_RUN=42822755938
EXPECTED_HEAD='b13083740f92c8b81b9b875b07fcb8635b8a6cf0'
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ('kernel','layout-report','addon','trustcache','out'): p.add_argument('--'+x,type=Path,required=True)
    p.add_argument('--run-id',type=int,required=True);p.add_argument('--head-sha',required=True)
    a=p.parse_args();raw=a.kernel.read_bytes();layout=json.loads(a.layout_report.read_text())
    need(a.run_id==EXPECTED_RUN and a.head_sha==EXPECTED_HEAD,'GitHub run identity mismatch')
    need(layout.get('status')=='DISPLAY_REFERENCE_LAYOUT_PASS' and layout.get('candidate_sha256')==sha(raw),
         'Layout report does not authenticate this compiled image')
    for marker in (b'nabu-iomfb-compat',b'NABU DISPLAY iomfb-compat selector='):
        need(raw.count(marker)>=1,'Compiled IOMFB compatibility marker missing: '+marker.decode())
    backend=verify(a.kernel)
    public=b'5c5a956febabc8c8f3fc7b2cc48ae22bcab9ae25a9853c7cd0baadc9ec406882'
    owner=b'1f69d64e12f380b9bc14cb03e825cb925edaaa335aa4bb258c78a40f405d71e3'
    need(raw.count(public)==1 and raw.count(owner)==0,'Unexpected ZAP metadata identity')
    final=raw.replace(public,owner)
    need(len(final)==len(raw) and final.count(owner)==1 and public not in final,'Owner ZAP replacement invalid')
    a.out.mkdir(parents=True,exist_ok=True)
    kernel=a.out/'kernel-iomfb-compat.macho';report=a.out/'kernel-preparation.json'
    need(not kernel.exists() and not report.exists(),'Prepared output already exists')
    kernel.write_bytes(final);transport=audit(kernel,a.addon,a.trustcache)
    result={'status':'STANDARD_COMPOSITOR_KERNEL_HOST_PASS','variant':'IOMFB_COMPAT',
      'source_run':a.run_id,'source_head':a.head_sha,'raw_kernel_sha256':sha(raw),
      'kernel_sha256':sha(final),'kernel_bytes':len(final),'kernel_path':str(kernel),
      'addon_path':str(a.addon.resolve()),'trustcache_path':str(a.trustcache.resolve()),
      'addon_sha256':transport['addon_sha256'],'trustcache_sha256':transport['trustcache_sha256'],
      'display_layout':layout,'compiled_backend':backend,'signed_transport':transport,
      'required_boot_arguments':['sheng-gpu-addon=1','nabu-ui-watch=1','sheng-vsync=60','nabu-gpu-scanout=1','nabu-iomfb-compat=1'],
      'compat_markers_verified':True,'boot_proven':False}
    report.write_text(json.dumps(result,indent=2)+'\n')
    print('IOMFB_COMPAT_KERNEL_HOST_PASS',result['kernel_sha256'],flush=True)
if __name__=='__main__': main()
