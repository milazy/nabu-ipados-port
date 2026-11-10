#!/usr/bin/env python3
"""Atomic nabu eight-core ADT + menu installation with exact rollback.

No system partitions, GPT, bootloader partitions, Android userdata, or Apple
root volumes are written.  This changes only ESP ADT and UniXNU menu after
verifying the known 2026-11-10 IOMFB modes baseline.
"""
import hashlib,json,subprocess,datetime,argparse,shlex,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--serial',required=True)
a=p.parse_args()
R=a.root.resolve();OUT=R/'build-artifacts/nabu-smp-integrated-host-20261110'
ADB=R/'platform-tools/adb.exe';S=a.serial
REC=OUT/'install-receipt.json';CAND=json.loads((OUT/'preflight.json').read_text())
MENU='/esp/EFI/UniXNU/unixnu.toml'
K='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
ADT=K+'.adt';TC=K+'.trustcache';ADDON=K+'.gpuaddon';DATA='/esp/EFI/UniXNU/Payloads/owner-data-1g-packed.dbr'
BASE={MENU:'7387bc2b95b876bb715107a5427728cd1f2115d06af3155aa7f20da5606278bb',
 ADT:'0b6e519bf5b187fe5c311639f4b121a91dce820e25aaeba29a0525fd0d443b69',
 K:'7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d',
 TC:'985f504f98ac96b69f04025934363b8e65da4fdc7236e0bc7cb3e87edf8a8457',
 ADDON:'6063ea23e49233479338d756c25e127d52c40da786018b4ed5212112dfc6c7d7',
 DATA:'2bbe5c0d3626eeadad42d7223fc1a877d0665541bea6c44d95b7dc6e0400380f'}
def need(cond,msg):
 if not cond:raise RuntimeError('STOP: '+msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def adb(*args):
 q=subprocess.run([str(ADB),'-s',S,*map(str,args)],capture_output=True,timeout=150)
 need(q.returncode==0,'ADB error '+repr(args)+' '+q.stderr.decode(errors='replace')[-350:])
 return q.stdout.decode(errors='replace').strip()
def sh(s):return adb('shell',s)
def remote_sha(path):return sh('sha256sum '+shlex.quote(path)).split()[0]
def mount(ro):
 sh('sync; umount /esp 2>/dev/null || true')
 sh('blockdev --set'+('ro ' if ro else 'rw ')+'/dev/block/sda29')
 need(sh('blockdev --getro /dev/block/sda29')==('1' if ro else '0'),'ESP block mode mismatch')
 sh('mkdir -p /esp; mount -t vfat -o '+('ro' if ro else 'rw,sync')+' /dev/block/sda29 /esp')
 need((' ro,' if ro else ' rw,') in sh("cat /proc/mounts | grep ' /esp '"),'ESP mount mode mismatch')
def verify(rows):
 for target,h in rows.items():need(remote_sha(target)==h,'Device hash mismatch '+target)

need(not REC.exists(),'An installation receipt already exists')
need(CAND['status']=='EIGHTCORE_ADT_MENU_HOST_PREP_PASS_NOT_FLASHED','Host preflight has not passed')
newadt=OUT/'kernel-eightcore.adt';newmenu=OUT/'unixnu.eightcore.toml';safe=OUT/'unixnu.eightcore-safe.toml'
oldadt=R/'build-artifacts/nabu-memory-ui-20261110/kernel-memory-ui.macho.adt'
oldmenu=R/'build-artifacts/nabu-iomfb-modes-20261110/unixnu.iomfb-modes.toml'
need(sha(newadt)==CAND['new_adt_sha256'],'Prepared ADT changed')
need(sha(newmenu)==CAND['new_menu_sha256'],'Prepared menu changed')
need(sha(oldadt)==BASE[ADT] and sha(oldmenu)==BASE[MENU],'Rollback image changed')
need(adb('get-state')=='recovery','Tablet is not in TWRP recovery')
need(sh('getprop ro.product.device')=='nabu' and 'uid=0(root)' in sh('id'),'Wrong device or no root')
need(int(sh('cat /sys/class/power_supply/battery/capacity'))>=25,'Battery below 25 percent')
need(sh('blockdev --getsize64 /dev/block/sda29')=='1073741824','Wrong ESP size')
mount(True);verify(BASE)
need(int(sh('df -k /esp | tail -1').split()[3])*1024>4*1024*1024,'Insufficient ESP headroom')
bakmenu='/esp/EFI/UniXNU/unixnu.pre-eightcore-20261110.toml'
bakadt=ADT+'.pre-eightcore-20261110'
need(sh('if [ -e '+bakmenu+' ] || [ -e '+bakadt+' ]; then echo TAKEN; else echo FREE; fi')=='FREE','Persistent backup path occupied')
pairs=[(newadt,'/tmp/eightcore-new.adt'),(newmenu,'/tmp/eightcore-new.toml'),
       (safe,'/tmp/eightcore-safe.toml'),(oldadt,'/tmp/eightcore-old.adt'),(oldmenu,'/tmp/eightcore-old.toml')]
for local,remote in pairs:
 sh('rm -f '+remote);adb('push',local,remote);need(remote_sha(remote)==sha(local),'RAM stage mismatch '+remote)
written=False
try:
 mount(False);verify(BASE)
 sh('cp '+MENU+' '+bakmenu+'; cp '+ADT+' '+bakadt+'; sync')
 need(remote_sha(bakmenu)==BASE[MENU] and remote_sha(bakadt)==BASE[ADT],'Persistent rollback backup corrupted')
 written=True
 sh('cp /tmp/eightcore-safe.toml '+MENU+'; sync')
 need(remote_sha(MENU)==sha(safe),'Interim safe menu invalid')
 sh('cp /tmp/eightcore-new.adt '+ADT+'; sync')
 need(remote_sha(ADT)==sha(newadt),'ADT installation readback invalid')
 # The existing verified kernel, Metal, trustcache, and owner Data are not modified.
 for x in (K,TC,ADDON,DATA):need(remote_sha(x)==BASE[x],'Protected payload changed '+x)
 sh('cp /tmp/eightcore-new.toml '+MENU+'; sync')
 need(remote_sha(MENU)==sha(newmenu),'Final menu invalid')
except Exception:
 if written:
  sh('cp /tmp/eightcore-old.adt '+ADT+'; cp /tmp/eightcore-old.toml '+MENU+'; sync')
  need(remote_sha(ADT)==BASE[ADT] and remote_sha(MENU)==BASE[MENU],
       'ROLLBACK NOT VERIFIED - RETAIN RECOVERY')
  print('ROLLBACK_SHA_VERIFIED',flush=True)
 raise
finally:
 mount(True)
verify({**{x:BASE[x] for x in (K,TC,ADDON,DATA)},ADT:sha(newadt),MENU:sha(newmenu)})
result={'status':'EIGHTCORE_ADT_MENU_INSTALL_PASS_BOOT_UNVERIFIED',
 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'cpu_affinities':CAND['cpu_affinities'],'psci_method':'smc',
 'installed_adt_sha256':sha(newadt),'installed_menu_sha256':sha(newmenu),
 'protected_payload_hashes':{x:BASE[x] for x in (K,TC,ADDON,DATA)},
 'rollback_adt_sha256':BASE[ADT],'rollback_menu_sha256':BASE[MENU],
 'esp_readonly_after':sh('blockdev --getro /dev/block/sda29')=='1',
 'android_or_gpt_modified':False,'apple_root_or_data_modified':False,
 'screen_verified':False,'render_frames_verified':False}
REC.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
