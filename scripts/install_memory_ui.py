from pathlib import Path
import subprocess,json,hashlib,tomllib,datetime,shlex,sys,argparse
p=argparse.ArgumentParser(description='Install the hash-checked 2 GiB memory/UI repair; explicit device authorization required.')
p.add_argument('--root',type=Path,required=True)
p.add_argument('--serial',required=True)
args=p.parse_args()
R=args.root.resolve()
OUT=R/'build-artifacts/nabu-memory-ui-20261110'
REPORT=OUT/'kernel-preparation.json';RECEIPT=OUT/'install-receipt.json'
ADB=R/'platform-tools/adb.exe';SER=args.serial;ESP='/dev/block/sda29'
MENU='/esp/EFI/UniXNU/unixnu.toml';K='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho';TC=K+'.trustcache'
OLDK=R/'build-artifacts/nabu-standard-compositor-20261110/kernel-standard-compositor.macho'
OLDTC=R/'build-artifacts/nabu-standard-compositor-20261110/kernel-standard-compositor.macho.trustcache'
OLDMENU=R/'build-artifacts/nabu-standard-compositor-20261110/unixnu.standard-compositor.toml'
OLDADT=OUT/'kernel-before.adt';NEWADT=OUT/'kernel-memory-ui.macho.adt';ADT=K+'.adt'
OLD={'kernel':'dc260d7980a9f0baadd8730f14e3659fa1975c88ab8d917f14851c21055037a4','trustcache':'0a5679e8a6d49228a4c9bda6b6b0363b50e96f74047847dbb943c3aa426739b5','menu':'e917bc95db124a4ae55ea603a51c5a9ab4cf2fc676b8433db540b45fc2ed5b62','adt':'658e38300dfd05e9a8c03e4c44790192c313949b627c72dfdb9144c7c889f12c'}
PROTECTED={TC:OLD['trustcache'],K+'.gpuaddon':'8ff3cea1a75be938f10be7ba4f058db0b815157d8d1b15ab19d076fa620a8949','/esp/EFI/UniXNU/Payloads/owner-data-1g-packed.dbr':'2bbe5c0d3626eeadad42d7223fc1a877d0665541bea6c44d95b7dc6e0400380f'}
def need(ok,why):
    if not ok:raise RuntimeError('STOP: '+why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def adb(*args):
    r=subprocess.run([str(ADB),'-s',SER,*map(str,args)],capture_output=True,timeout=240)
    need(r.returncode==0,'ADB failed '+repr(args)+' '+r.stderr.decode(errors='replace')[-250:])
    return r.stdout.decode(errors='replace').strip()
def shell(s):return adb('shell',s)
def rhash(p):return shell('sha256sum '+shlex.quote(p)).split()[0]
def mount(ro):
    shell('sync; umount /esp 2>/dev/null || true; blockdev --set'+('ro ' if ro else 'rw ')+ESP)
    need(shell('blockdev --getro '+ESP)==('1' if ro else '0'),'Block readonly state mismatch')
    shell('mkdir -p /esp; mount -t vfat -o '+('ro' if ro else 'rw,sync')+' '+ESP+' /esp')
    need((' ro,' if ro else ' rw,') in shell("cat /proc/mounts | grep ' /esp '"),'Mount state mismatch')
def check_protected():
    for p,h in PROTECTED.items():need(rhash(p)==h,'Protected payload changed '+p)
def main():
    need(not RECEIPT.exists(),'Install receipt already exists')
    r=json.loads(REPORT.read_text());need(r['status']=='STANDARD_COMPOSITOR_KERNEL_HOST_PASS','Preparation failed')
    newk=Path(r['kernel_path']);newtc=Path(r['trustcache_path'])
    memory=json.loads((OUT/'memory-window-preparation.json').read_text())
    need(memory['status']=='NABU_RESERVED_MEMORY_WINDOW_HOST_PASS' and memory['old_bytes']==0x40000000 and memory['new_bytes']==0x80000000,'Memory report mismatch')
    need(sha(OLDADT)==OLD['adt'] and sha(NEWADT)==memory['new_sha256'],'ADT input mismatch')
    need(r['trustcache_sha256']==OLD['trustcache'],'Paired trust cache must remain unchanged')
    need(sha(newk)==r['kernel_sha256'] and sha(newtc)==r['trustcache_sha256'],'Prepared bytes changed')
    need(sha(OLDK)==OLD['kernel'] and sha(OLDTC)==OLD['trustcache'] and sha(OLDMENU)==OLD['menu'],'Rollback input mismatch')
    sys.path.insert(0,str(R/'nabu-ipados-macos-build/ci'))
    from audit_compositor_transport import audit
    audit(newk,Path(r['addon_path']),newtc)
    text=OLDMENU.read_text(encoding='utf-8');d=tomllib.loads(text)
    e=next(x for x in d['entry'] if x['id']=='xnu-existing-ui-policy')
    fallback=next(x for x in d['entry'] if x['id']=='xnu-crypto384')
    need(fallback['type']=='xnu' and fallback['path']!=e['path'],'Independent fallback missing')
    oldargs=e['args'];tokens=oldargs.split()
    need(all(tokens.count(x)==1 for x in ('sheng-gpu-addon=1','nabu-ui-watch=1')) and not any(x.startswith('nabu-gpu-userprobe=') for x in tokens),'Existing standard transport mismatch')
    args=oldargs
    need(len(args.encode('ascii'))<1024,'Boot command too long')
    need(text.count('args = "'+oldargs+'"')==1,'Ambiguous args')
    text=text.replace('args = "'+oldargs+'"','args = "'+args+'"',1)
    text=text.replace('iPadOS 17.7 COMPOSITOR REPAIR (UNVERIFIED)','iPadOS 17.7 MEMORY 2GiB + UI TRACE (UNVERIFIED)',1)
    d=tomllib.loads(text);need(d['boot']['default']=='xnu-existing-ui-policy','Default changed unexpectedly')
    ne=next(x for x in d['entry'] if x['id']=='xnu-existing-ui-policy')
    need(ne['path']=='Payloads/kernel-fulltrace-panic.macho','Kernel path mismatch')
    for x in r['required_boot_arguments']:need(ne['args'].split().count(x)==1,'Boot argument missing '+x)
    menu=OUT/'unixnu.memory-ui.toml';menu.write_text(text,encoding='utf-8',newline='\n')
    safe=OUT/'unixnu.memory-ui-fallback.toml'
    safe.write_text(text.replace('default = "xnu-existing-ui-policy"','default = "xnu-crypto384"',1),encoding='utf-8',newline='\n')
    need(tomllib.loads(safe.read_text())['boot']['default']=='xnu-crypto384','Fallback default invalid')
    need(adb('get-state')=='recovery' and shell('getprop ro.product.device')=='nabu','Wrong device/state')
    need('uid=0(root)' in shell('id'),'Recovery root required')
    need(int(shell('cat /sys/class/power_supply/battery/capacity'))>=25,'Battery too low')
    mount(True)
    for p,h in ((K,OLD['kernel']),(TC,OLD['trustcache']),(ADT,OLD['adt']),(MENU,OLD['menu'])):need(rhash(p)==h,'Live baseline mismatch '+p)
    check_protected()
    free=int(shell('df -k /esp | tail -1').split()[3])*1024
    need(free>max(0,newk.stat().st_size-OLDK.stat().st_size)+newtc.stat().st_size+2*1024*1024,'Insufficient ESP space')
    staging=[(newk,'/tmp/memory-ui-new-kernel'),(NEWADT,'/tmp/memory-ui-new-adt'),(menu,'/tmp/memory-ui-new-menu'),(safe,'/tmp/memory-ui-safe-menu'),(OLDK,'/tmp/memory-ui-old-kernel'),(OLDADT,'/tmp/memory-ui-old-adt'),(OLDMENU,'/tmp/memory-ui-old-menu')]
    for local,remote in staging:
        need(shell('test -e '+remote+'; echo $?').splitlines()[-1]=='1','Staging already exists')
        adb('push',local,remote);need(rhash(remote)==sha(local),'RAM stage mismatch')
    backup='/esp/EFI/UniXNU/unixnu.pre-memory-ui-20261110.toml'
    need(shell('test -e '+backup+'; echo $?').splitlines()[-1]=='1','Backup already exists')
    changed=False
    try:
        mount(False)
        for p,h in ((K,OLD['kernel']),(TC,OLD['trustcache']),(ADT,OLD['adt']),(MENU,OLD['menu'])):need(rhash(p)==h,'Baseline changed on remount')
        shell('cp '+MENU+' '+backup+'; sync');need(rhash(backup)==OLD['menu'],'Backup mismatch')
        changed=True
        shell('cp /tmp/memory-ui-safe-menu '+MENU+'; sync');need(rhash(MENU)==sha(safe),'Fallback selection failed')
        shell('cp /tmp/memory-ui-new-kernel '+K+'; sync');need(rhash(K)==sha(newk),'Kernel write mismatch')
        shell('cp /tmp/memory-ui-new-adt '+ADT+'; sync');need(rhash(ADT)==sha(NEWADT),'ADT write mismatch')
        check_protected()
        shell('cp /tmp/memory-ui-new-menu '+MENU+'; sync');need(rhash(MENU)==sha(menu),'Final menu mismatch')
    except Exception:
        if changed:
            shell('cp /tmp/memory-ui-old-kernel '+K+'; cp /tmp/memory-ui-old-adt '+ADT+'; cp /tmp/memory-ui-old-menu '+MENU+'; sync')
            for p,h in ((K,OLD['kernel']),(TC,OLD['trustcache']),(ADT,OLD['adt']),(MENU,OLD['menu'])):need(rhash(p)==h,'ROLLBACK INCOMPLETE: keep recovery open')
            print('ROLLBACK_VERIFIED')
        raise
    finally:mount(True)
    for p,h in ((K,sha(newk)),(ADT,sha(NEWADT)),(TC,sha(newtc)),(MENU,sha(menu))):need(rhash(p)==h,'Read-only final mismatch')
    check_protected()
    result={'status':'MEMORY_UI_INSTALL_PASS_BOOT_UNVERIFIED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kernel_sha256':sha(newk),'trustcache_sha256':sha(newtc),'menu_sha256':sha(menu),'kernel_source_sha256':r['raw_kernel_sha256'],'adt_sha256':sha(NEWADT),'old_window_bytes':0x40000000,'requested_window_bytes':0x80000000,'firmware_allocation_proven':False,'protected_payloads_verified':PROTECTED,'ESP_readonly_after':True,'Android_GPT_modified':False,'Apple_partitions_modified':False,'boot_verified':False}
    RECEIPT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
