"""Install qualified Metal addon/trust/menu from recovery; explicit device authorization required."""
import argparse,datetime,hashlib,json,shlex,subprocess,sys,tomllib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True);p.add_argument('--serial',required=True)
a=p.parse_args();root=a.root.resolve();out=root/'build-artifacts/nabu-metal-async-20261110'
receipt=out/'install-receipt.json';adbexe=root/'platform-tools/adb.exe'
k='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho';tc=k+'.trustcache';addon=k+'.gpuaddon';menu='/esp/EFI/UniXNU/unixnu.toml';esp='/dev/block/sda29'
oldout=root/'build-artifacts/nabu-memory-ui-20261110'
old=json.loads((oldout/'install-receipt.json').read_text())
oldfiles={addon:root/'build-artifacts/nabu-gpu-ownerhash-offline-20261109/kernel-owner-zap-hash-test.macho.gpuaddon',tc:root/'build-artifacts/nabu-standard-compositor-20261110/kernel-standard-compositor.macho.trustcache',menu:oldout/'unixnu.memory-ui.toml'}
oldhash={addon:'8ff3cea1a75be938f10be7ba4f058db0b815157d8d1b15ab19d076fa620a8949',tc:old['trustcache_sha256'],menu:old['menu_sha256']}
protected={k:old['kernel_sha256'],k+'.adt':old['adt_sha256'],'/esp/EFI/UniXNU/Payloads/owner-data-1g-packed.dbr':'2bbe5c0d3626eeadad42d7223fc1a877d0665541bea6c44d95b7dc6e0400380f'}
def need(ok,why):
    if not ok:raise RuntimeError('STOP: '+why)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def adb(*args):
    r=subprocess.run([str(adbexe),'-s',a.serial,*map(str,args)],capture_output=True,timeout=240)
    need(r.returncode==0,'ADB failure '+r.stderr.decode(errors='replace')[-300:])
    return r.stdout.decode(errors='replace').strip()
def sh(command):return adb('shell',command)
def rhash(path):return sh('sha256sum '+shlex.quote(path)).split()[0]
def check(values):
    for path,digest in values.items():need(rhash(path)==digest,'Live fingerprint mismatch: '+path)
def mount(ro):
    sh('sync; umount /esp 2>/dev/null || true; blockdev --set'+('ro ' if ro else 'rw ')+esp)
    need(sh('blockdev --getro '+esp)==('1' if ro else '0'),'Block protection mismatch')
    sh('mkdir -p /esp; mount -t vfat -o '+('ro' if ro else 'rw,sync')+' '+esp+' /esp')
    need((' ro,' if ro else ' rw,') in sh("cat /proc/mounts | grep ' /esp '"),'Mount mode mismatch')
def main():
    need(not receipt.exists(),'Installation already recorded')
    prep=json.loads((out/'payload-preparation.json').read_text());need(prep['status']=='ASYNC_METAL_PAYLOAD_HOST_PASS','Preparation failed')
    sys.path.insert(0,str(root/'nabu-ipados-macos-build/ci'))
    from audit_compositor_transport import audit
    newaddon=Path(prep['addon_path']);newtc=Path(prep['trustcache_path'])
    need(sha(newaddon)==prep['addon_sha256'] and sha(newtc)==prep['trustcache_sha256'],'Prepared input changed')
    audit(Path(prep['kernel_path']),newaddon,newtc)
    for path,local in oldfiles.items():need(sha(local)==oldhash[path],'Rollback input mismatch')
    text=oldfiles[menu].read_text();parsed=tomllib.loads(text)
    entry=next(x for x in parsed['entry'] if x['id']=='xnu-existing-ui-policy')
    fallback=next(x for x in parsed['entry'] if x['id']=='xnu-crypto384')
    need(fallback['type']=='xnu' and fallback['path']!=entry['path'],'Independent fallback missing')
    need(parsed['boot']['default']==entry['id'] and entry['path']=='Payloads/kernel-fulltrace-panic.macho','Unexpected boot selection')
    need(all(entry['args'].split().count(x)==1 for x in ('sheng-gpu-addon=1','nabu-ui-watch=1')),'Standard transport flags missing')
    title='iPadOS 17.7 MEMORY 2GiB + UI TRACE (UNVERIFIED)';need(text.count(title)==1,'Menu title drift')
    text=text.replace(title,'iPadOS 17.7 METAL ASYNC REPAIR (UNVERIFIED)',1)
    newmenu=out/'unixnu.metal-async.toml';newmenu.write_text(text,encoding='utf-8',newline='\n')
    safe=out/'unixnu.metal-async-fallback.toml';safe.write_text(text.replace('default = "xnu-existing-ui-policy"','default = "xnu-crypto384"',1),encoding='utf-8',newline='\n')
    need(tomllib.loads(safe.read_text())['boot']['default']=='xnu-crypto384','Fallback selection failed')
    need(adb('get-state')=='recovery' and sh('getprop ro.product.device')=='nabu' and 'uid=0(root)' in sh('id'),'Wrong device/state')
    need(int(sh('cat /sys/class/power_supply/battery/capacity'))>=25,'Battery low')
    mount(True);check(oldhash);check(protected)
    need(sh('blockdev --getsize64 '+esp)=='1073741824','ESP size changed')
    free=int(sh('df -k /esp | tail -1').split()[3])*1024
    need(free>max(0,newaddon.stat().st_size-oldfiles[addon].stat().st_size)+newtc.stat().st_size+2*1024*1024,'ESP space insufficient')
    changes=[(newaddon,addon),(newtc,tc),(newmenu,menu)]
    stages=[]
    for index,(local,remote) in enumerate(changes):
        stages.extend([(local,f'/tmp/metal-async-new-{index}'),(oldfiles[remote],f'/tmp/metal-async-old-{index}')])
    stages.append((safe,'/tmp/metal-async-safe-menu'))
    for local,remote in stages:
        need(sh('test -e '+remote+'; echo $?').splitlines()[-1]=='1','Stage already exists')
        adb('push',local,remote);need(rhash(remote)==sha(local),'RAM stage mismatch')
    backup='/esp/EFI/UniXNU/unixnu.pre-metal-async-20261110.toml'
    need(sh('test -e '+backup+'; echo $?').splitlines()[-1]=='1','Backup exists')
    changed=False
    try:
        mount(False);check(oldhash);check(protected)
        sh('cp '+menu+' '+backup+'; sync');need(rhash(backup)==oldhash[menu],'Backup mismatch')
        changed=True
        sh('cp /tmp/metal-async-safe-menu '+menu+'; sync');need(rhash(menu)==sha(safe),'Fallback write mismatch')
        for index,(local,remote) in enumerate(changes):
            sh(f'cp /tmp/metal-async-new-{index} '+remote+'; sync');need(rhash(remote)==sha(local),'Payload write mismatch')
        check(protected)
    except Exception:
        if changed:
            for index,(_,remote) in enumerate(changes):sh(f'cp /tmp/metal-async-old-{index} '+remote+'; sync')
            check(oldhash);check(protected);print('ROLLBACK_VERIFIED',flush=True)
        raise
    finally:mount(True)
    expected={remote:sha(local) for local,remote in changes};check(expected);check(protected)
    result={'status':'ASYNC_METAL_INSTALL_PASS_BOOT_UNVERIFIED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kernel_sha256':protected[k],'adt_sha256':protected[k+'.adt'],'addon_sha256':expected[addon],'trustcache_sha256':expected[tc],'menu_sha256':expected[menu],'verified_sha256':{**expected,**protected},'ESP_readonly_after':True,'kernel_or_ADT_modified':False,'Android_GPT_modified':False,'Apple_partitions_modified':False,'boot_verified':False}
    receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
