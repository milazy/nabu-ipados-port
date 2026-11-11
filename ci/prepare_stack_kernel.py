#!/usr/bin/env python3
"""Prepare the user-stack-sampler kernel (integrated UI build + ci/apply_ui_stack_sampler.py).

Same gates as prepare_iomfb_modes.py (layout report authenticates the image, IOMFB markers, CPU display
backend, public->owner ZAP replacement) plus the NabuStack sampler strings. The signed transport audit
runs against the installed check-fix addon and trust cache, which this kernel is paired with.
"""
import argparse,hashlib,json
from pathlib import Path
from audit_compositor_transport import audit,need
from verify_cpu_display_backend import verify

def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ('kernel','layout-report','addon','trustcache','out'): p.add_argument('--'+x,type=Path,required=True)
    p.add_argument('--run-id',type=int,required=True)
    a=p.parse_args();raw=a.kernel.read_bytes();layout=json.loads(a.layout_report.read_text())
    need(layout.get('status')=='DISPLAY_REFERENCE_LAYOUT_PASS' and layout.get('candidate_sha256')==sha(raw),
         'Layout report does not authenticate this compiled image')
    for marker in (b'nabu-iomfb-compat',b'NABU DISPLAY iomfb-compat selector=',b'NABU DISPLAY iomfb-modes published',
                   b'NABU DISPLAY iomfb-mode block=0x40',b'nabu-ui-watch',
                   b'NabuStack: s=%u %s pid=%d threads=%u/%u sr_base=%llx sr_slide=%llx',
                   b'NabuStack: s=%u pid=%d tid=%llu st=%x h=%u w=%llx pc=%llx lr=%llx sp=%llx fp=%llx n=%u',
                   b'liveactivitiesd',b'chronod',b'nabu ram-data',b'launchd override disables watchdogd chronod liveactivitiesd'):
        need(raw.count(marker)>=1,'Compiled marker missing: '+marker.decode())
    backend=verify(a.kernel)
    public=b'5c5a956febabc8c8f3fc7b2cc48ae22bcab9ae25a9853c7cd0baadc9ec406882'
    owner=b'1f69d64e12f380b9bc14cb03e825cb925edaaa335aa4bb258c78a40f405d71e3'
    need(raw.count(public)==1 and raw.count(owner)==0,'Unexpected ZAP metadata identity')
    final=raw.replace(public,owner)
    need(len(final)==len(raw) and final.count(owner)==1 and public not in final,'Owner ZAP replacement invalid')
    a.out.mkdir(parents=True,exist_ok=True)
    kernel=a.out/'kernel-widget-off.macho';report=a.out/'kernel-preparation.json'
    need(not kernel.exists() and not report.exists(),'Prepared output already exists')
    kernel.write_bytes(final);transport=audit(kernel,a.addon,a.trustcache)
    result={'status':'STACK_SAMPLER_KERNEL_HOST_PASS','source_run':a.run_id,'raw_kernel_sha256':sha(raw),
      'kernel_sha256':sha(final),'kernel_bytes':len(final),'addon_sha256':transport['addon_sha256'],
      'trustcache_sha256':transport['trustcache_sha256'],'display_layout':layout,'compiled_backend':backend,
      'signed_transport':transport,'boot_proven':False}
    report.write_text(json.dumps(result,indent=2,default=str)+'\n')
    print('STACK_SAMPLER_KERNEL_HOST_PASS',result['kernel_sha256'],flush=True)
if __name__=='__main__': main()
