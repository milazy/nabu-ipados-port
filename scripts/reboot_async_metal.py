"""Verify the installed async frontend repair and request one authorized reboot."""
import argparse,datetime,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True);p.add_argument('--serial',required=True)
a=p.parse_args();out=a.root/'build-artifacts/nabu-metal-async-20261110'
r=json.loads((out/'install-receipt.json').read_text())
assert r['status']=='ASYNC_METAL_INSTALL_PASS_BOOT_UNVERIFIED'
assert not (out/'reboot-receipt.json').exists(),'Reboot already recorded'
def adb(*args):
    result=subprocess.run([str(a.root/'platform-tools/adb.exe'),'-s',a.serial,*args],capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError(result.stderr[-400:])
    return result.stdout.strip()
assert adb('get-state')=='recovery'
assert adb('shell','getprop ro.product.device')=='nabu'
assert adb('shell','blockdev --getro /dev/block/sda29')=='1'
assert ' ro,' in adb('shell',"cat /proc/mounts | grep ' /esp '")
for path,digest in r['verified_sha256'].items():
    assert adb('shell','sha256sum '+path).split()[0]==digest,'Final fingerprint mismatch: '+path
result={'status':'ASYNC_METAL_FINAL_READBACK_PASS_REBOOT_ACCEPTED_UI_UNVERIFIED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verified_sha256':r['verified_sha256'],'ESP_readonly_before_reboot':True,'boot_verified':False}
adb('reboot')
(out/'reboot-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
