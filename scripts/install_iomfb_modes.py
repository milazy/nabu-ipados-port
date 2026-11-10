from pathlib import Path
import argparse,subprocess,json,hashlib,tomllib,datetime,shlex,sys

p=argparse.ArgumentParser(description='Install IOMFB compatibility kernel over the verified async-Metal baseline.')
p.add_argument('--root',type=Path,required=True);p.add_argument('--serial',required=True)
a=p.parse_args();R=a.root.resolve();SER=a.serial
OUT=R/'build-artifacts/nabu-iomfb-modes-20261110'
REPORT=OUT/'kernel-preparation.json';RECEIPT=OUT/'install-receipt.json'
ADB=R/'platform-tools/adb.exe';ESP='/dev/block/sda29'
MENU='/esp/EFI/UniXNU/unixnu.toml';K='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
TC=K+'.trustcache';ADT=K+'.adt';ADDON=K+'.gpuaddon';DATA='/esp/EFI/UniXNU/Payloads/owner-data-1g-packed.dbr'
OLDK=R/'build-artifacts/nabu-iomfb-compat-20261110/kernel-iomfb-compat.macho'
OLDMENU=R/'build-artifacts/nabu-iomfb-compat-20261110/unixnu.iomfb-compat.toml'
BASE={
 K:'c2f60aa6922ceb405f47ae6d7f0dd5b364968a37e8e8601afd8d0675f76d4ea2',
 TC:'985f504f98ac96b69f04025934363b8e65da4fdc7236e0bc7cb3e87edf8a8457',
 ADT:'0b6e519bf5b187fe5c311639f4b121a91dce820e25aaeba29a0525fd0d443b69',
 ADDON:'6063ea23e49233479338d756c25e127d52c40da786018b4ed5212112dfc6c7d7',
 DATA:'2bbe5c0d3626eeadad42d7223fc1a877d0665541bea6c44d95b7dc6e0400380f',
 MENU:'30b997a2e04a66bfedd6df06e96a3db14e8db0271e6821a1f7f10cc577f9164c'}

def need(v,m):
    if not v: raise RuntimeError('STOP: '+m)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def adb(*args):
    q=subprocess.run([str(ADB),'-s',SER,*map(str,args)],capture_output=True,timeout=240)
    need(q.returncode==0,'ADB '+repr(args)+' '+q.stderr.decode(errors='replace')[-300:])
    return q.stdout.decode(errors='replace').strip()
def sh(s): return adb('shell',s)
def rhash(p): return sh('sha256sum '+shlex.quote(p)).split()[0]
def mount(ro):
    sh('sync; umount /esp 2>/dev/null || true; blockdev --set'+('ro ' if ro else 'rw ')+ESP)
    need(sh('blockdev --getro '+ESP)==('1' if ro else '0'),'ESP readonly bit')
    sh('mkdir -p /esp; mount -t vfat -o '+('ro' if ro else 'rw,sync')+' '+ESP+' /esp')
    need((' ro,' if ro else ' rw,') in sh("cat /proc/mounts | grep ' /esp '"),'ESP mount mode')
def check(mapping):
    for path,digest in mapping.items(): need(rhash(path)==digest,'hash drift '+path)

need(not RECEIPT.exists(),'install already recorded')
r=json.loads(REPORT.read_text())
need(r['status']=='STANDARD_COMPOSITOR_KERNEL_HOST_PASS' and r.get('variant')=='IOMFB_MODES','kernel preparation not qualified')
newk=Path(r['kernel_path']);need(sha(newk)==r['kernel_sha256'],'prepared kernel changed')
need(r['trustcache_sha256']==BASE[TC] and r['addon_sha256']==BASE[ADDON],'transport baseline changed')
need(sha(OLDK)==BASE[K] and sha(OLDMENU)==BASE[MENU],'local rollback baseline mismatch')

text=OLDMENU.read_text(encoding='utf-8');parsed=tomllib.loads(text)
entry=next(x for x in parsed['entry'] if x['id']=='xnu-existing-ui-policy')
fallback=next(x for x in parsed['entry'] if x['id']=='xnu-crypto384')
need(parsed['boot']['default']=='xnu-existing-ui-policy','unexpected current default')
need(entry['path']=='Payloads/kernel-fulltrace-panic.macho' and fallback['path']!=entry['path'],'fallback not independent')
tokens=entry['args'].split();need(tokens.count('nabu-iomfb-compat=1')==1,'compat baseline not enabled')
for token in ('sheng-gpu-addon=1','nabu-ui-watch=1','sheng-vsync=60','nabu-gpu-scanout=1'):
    need(tokens.count(token)==1,'missing current runtime flag '+token)
oldargs=entry['args'];newargs=oldargs
need(len(newargs.encode('ascii'))<1024,'boot arguments too long')
needle='args = "'+oldargs+'"';need(text.count(needle)==1,'ambiguous target args')
text=text.replace(needle,'args = "'+newargs+'"',1)
oldtitle='iPadOS 17.7 IOMFB COMPAT + METAL (UNVERIFIED)'
need(text.count(oldtitle)==1,'current title drift')
text=text.replace(oldtitle,'iPadOS 17.7 IOMFB MODES + METAL (UNVERIFIED)',1)
menu=OUT/'unixnu.iomfb-modes.toml';safe=OUT/'unixnu.iomfb-modes-fallback.toml'
OUT.mkdir(parents=True,exist_ok=True)
menu.write_text(text,encoding='utf-8',newline='\n')
safe.write_text(text.replace('default = "xnu-existing-ui-policy"','default = "xnu-crypto384"',1),encoding='utf-8',newline='\n')
need(tomllib.loads(menu.read_text())['boot']['default']=='xnu-existing-ui-policy','new default invalid')
need(tomllib.loads(safe.read_text())['boot']['default']=='xnu-crypto384','safe default invalid')
ne=next(x for x in tomllib.loads(menu.read_text())['entry'] if x['id']=='xnu-existing-ui-policy')
need(ne['args'].split().count('nabu-iomfb-compat=1')==1,'compat flag missing')

need(adb('get-state')=='recovery' and sh('getprop ro.product.device')=='nabu','wrong device/state')
need('uid=0(root)' in sh('id'),'recovery root required')
need(int(sh('cat /sys/class/power_supply/battery/capacity'))>=25,'battery too low')
mount(True);check(BASE)
free=int(sh('df -k /esp | tail -1').split()[3])*1024
need(free>max(0,newk.stat().st_size-OLDK.stat().st_size)+4*1024*1024,'ESP free space')
stages=[(newk,'/tmp/iomfb-new-kernel'),(menu,'/tmp/iomfb-new-menu'),(safe,'/tmp/iomfb-safe-menu'),
        (OLDK,'/tmp/iomfb-old-kernel'),(OLDMENU,'/tmp/iomfb-old-menu')]
for local,remote in stages:
    sh('rm -f '+remote);adb('push',local,remote);need(rhash(remote)==sha(local),'RAM stage mismatch '+remote)
backup='/esp/EFI/UniXNU/unixnu.pre-iomfb-modes-20261110.toml'
need(sh('test -e '+backup+'; echo $?').splitlines()[-1]=='1','persistent backup already exists')
changed=False
try:
    mount(False);check(BASE)
    sh('cp '+MENU+' '+backup+'; sync');need(rhash(backup)==BASE[MENU],'menu backup mismatch');changed=True
    sh('cp /tmp/iomfb-safe-menu '+MENU+'; sync');need(rhash(MENU)==sha(safe),'safe selection failed')
    sh('cp /tmp/iomfb-new-kernel '+K+'; sync');need(rhash(K)==sha(newk),'kernel write mismatch')
    # ADT, trust cache, async Metal addon and packed Data are deliberately untouched.
    for path in (TC,ADT,ADDON,DATA): need(rhash(path)==BASE[path],'protected payload changed '+path)
    sh('cp /tmp/iomfb-new-menu '+MENU+'; sync');need(rhash(MENU)==sha(menu),'final menu mismatch')
except Exception:
    if changed:
        sh('cp /tmp/iomfb-old-kernel '+K+'; cp /tmp/iomfb-old-menu '+MENU+'; sync')
        need(rhash(K)==BASE[K] and rhash(MENU)==BASE[MENU],'ROLLBACK INCOMPLETE - keep recovery open')
        print('ROLLBACK_VERIFIED',flush=True)
    raise
finally:
    mount(True)
final={K:sha(newk),MENU:sha(menu),TC:BASE[TC],ADT:BASE[ADT],ADDON:BASE[ADDON],DATA:BASE[DATA]}
check(final)
result={'status':'IOMFB_MODES_INSTALL_PASS_BOOT_UNVERIFIED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'kernel_sha256':sha(newk),'kernel_source_sha256':r['raw_kernel_sha256'],'menu_sha256':sha(menu),
        'protected_sha256':{x:final[x] for x in (TC,ADT,ADDON,DATA)},'compat_boot_arg':'nabu-iomfb-compat=1',
        'ESP_readonly_after':True,'Android_GPT_modified':False,'Apple_partitions_modified':False,'boot_verified':False}
RECEIPT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
