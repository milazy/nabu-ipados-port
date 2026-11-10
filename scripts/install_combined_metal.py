#!/usr/bin/env python3
"""Guarded ESP-only combined Metal addon deployment. Does NOT claim UI success."""
import argparse,subprocess,hashlib,json,datetime,shlex
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--serial',required=True);p.add_argument('--dry-run',action='store_true')
a=p.parse_args();R=a.root.resolve();S=a.serial;ADB=R/'platform-tools/adb.exe'
OUT=R/'build-artifacts/nabu-metal-combined-20261110'
REPORT=OUT/'payload-preparation.json'
REC=OUT/'install-receipt.json'
K='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
ADDON=K+'.gpuaddon';TC=K+'.trustcache';ADT=K+'.adt'
MENU='/esp/EFI/UniXNU/unixnu.toml'
DATA='/esp/EFI/UniXNU/Payloads/owner-data-1g-packed.dbr'
BASE={K:'7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d',
       ADT:'429d9e7f39da10fb373b4a05081b9817843fe6c8e86e10728ac8fb74f7fbb514',
       MENU:'a7c022ab15e885546e860bd7612bcf623ad3c37adc6d90d5cf5100384f02bdd7',
       DATA:'2bbe5c0d3626eeadad42d7223fc1a877d0665541bea6c44d95b7dc6e0400380f',
       ADDON:'6063ea23e49233479338d756c25e127d52c40da786018b4ed5212112dfc6c7d7',
       TC:'985f504f98ac96b69f04025934363b8e65da4fdc7236e0bc7cb3e87edf8a8457'}
def need(ok,msg):
    if not ok:raise RuntimeError('STOP BEFORE REBOOT: '+msg)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def adb(*args):
    c=subprocess.run([str(ADB),'-s',S,*map(str,args)],capture_output=True,timeout=300)
    need(c.returncode==0,repr(args)+' '+c.stderr.decode(errors='replace')[-320:])
    return c.stdout.decode(errors='replace').strip()
def sh(cmd):return adb('shell',cmd)
def rh(path):return sh('sha256sum '+shlex.quote(path)).split()[0]
def mount(ro):
    sh('sync; umount /esp 2>/dev/null || true; blockdev --set'+('ro ' if ro else 'rw ')+'/dev/block/sda29')
    need(sh('blockdev --getro /dev/block/sda29')==('1' if ro else '0'),'ESP block mode mismatch')
    sh('mkdir -p /esp; mount -t vfat -o '+('ro' if ro else 'rw,sync')+' /dev/block/sda29 /esp')
    need((' ro,' if ro else ' rw,') in sh("cat /proc/mounts | grep ' /esp '"),'ESP mount mode mismatch')
def checks(v):
    for f,digest in v.items(): need(rh(f)==digest,'hash drift '+f)
need(REPORT.is_file(),'Prepared payload missing')
r=json.loads(REPORT.read_text())
need(r['status']=='COMBINED_METAL_PAYLOAD_HOST_PASS','Combined payload not qualified')
addon=OUT/'kernel-metal-combined.macho.gpuaddon'
trust=OUT/'kernel-metal-combined.macho.trustcache'
need(sha(addon)==r['addon_sha256'] and sha(trust)==r['trustcache_sha256'],'Local payload mutated')
need(sha(addon)!=BASE[ADDON] and sha(trust)!=BASE[TC],'No new signatures')
oldaddon=R/'build-artifacts/nabu-metal-async-20261110/kernel-metal-async.macho.gpuaddon'
oldtrust=R/'build-artifacts/nabu-metal-async-20261110/kernel-metal-async.macho.trustcache'
need(sha(oldaddon)==BASE[ADDON] and sha(oldtrust)==BASE[TC],'Rollback bytes missing')
need(not REC.exists(),'Install already recorded')
if a.dry_run:
    print('COMBINED_METAL_LOCAL_PRECHECK_PASS',sha(addon),sha(trust),flush=True);raise SystemExit(0)
need(adb('get-state')=='recovery' and sh('getprop ro.product.device')=='nabu','Not the expected nabu recovery')
need('uid=0(root)' in sh('id'),'Root not available')
need(int(sh('cat /sys/class/power_supply/battery/capacity'))>=25,'Battery below 25 percent')
need(sh('blockdev --getsize64 /dev/block/sda29')=='1073741824','ESP identity/size mismatch')
mount(True);checks(BASE)
need(int(sh('df -k /esp | tail -1').split()[3])*1024>addon.stat().st_size+oldaddon.stat().st_size+5*1024*1024,'ESP insufficient free space for transaction')
oldaddon_esp=ADDON+'.pre-combined-20261110'
oldtrust_esp=TC+'.pre-combined-20261110'
need(sh('if [ -e '+oldaddon_esp+' ] || [ -e '+oldtrust_esp+' ]; then echo PRESENT; else echo CLEAR; fi')=='CLEAR','Persistent backup already present')
for local,path in ((addon,'/tmp/nabu-combined-new.gpuaddon'),(trust,'/tmp/nabu-combined-new.trustcache'),
                   (oldaddon,'/tmp/nabu-combined-old.gpuaddon'),(oldtrust,'/tmp/nabu-combined-old.trustcache')):
    sh('rm -f '+path);adb('push',local,path);need(rh(path)==sha(local),'RAM stage mismatch '+path)
protected={k:v for k,v in BASE.items() if k not in (ADDON,TC)}
written=False
try:
    mount(False);checks(BASE)
    sh('cp '+ADDON+' '+oldaddon_esp+'; cp '+TC+' '+oldtrust_esp+'; sync')
    need(rh(oldaddon_esp)==BASE[ADDON] and rh(oldtrust_esp)==BASE[TC],'Persistent backups invalid')
    written=True
    sh('cp /tmp/nabu-combined-new.gpuaddon '+ADDON+'; sync')
    need(rh(ADDON)==sha(addon),'Addon write-readback invalid')
    sh('cp /tmp/nabu-combined-new.trustcache '+TC+'; sync')
    need(rh(TC)==sha(trust),'Trust write-readback invalid')
    checks(protected)
except Exception:
    if written:
        sh('cp /tmp/nabu-combined-old.gpuaddon '+ADDON+'; cp /tmp/nabu-combined-old.trustcache '+TC+'; sync')
        need(rh(ADDON)==BASE[ADDON] and rh(TC)==BASE[TC],'ROLLBACK FAILED; do not reboot')
        print('ROLLBACK_COMPLETE_HASHES_VERIFIED',flush=True)
    raise
finally:
    mount(True)
checks({**protected,ADDON:sha(addon),TC:sha(trust)})
result={'status':'COMBINED_METAL_INSTALL_PASS_BOOT_UNVERIFIED',
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'new_addon_sha256':sha(addon),'new_trustcache_sha256':sha(trust),
        'old_addon_sha256':BASE[ADDON],'old_trustcache_sha256':BASE[TC],
        'protected_payload_hashes':protected,'esp_readonly':True,
        'android_modified':False,'ios_system_data_modified':False,'ui_verified':False}
REC.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
