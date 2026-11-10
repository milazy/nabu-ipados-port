#!/usr/bin/env python3
"""Apply supported UI policy to the existing kernel; preserve kernel and all payloads."""
from pathlib import Path
import argparse,datetime,hashlib,json,runpy,subprocess,tomllib

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lab',type=Path,required=True)
    a=ap.parse_args()
    lab=a.lab.resolve()
    h=runpy.run_path(str(lab/'INSTALL_INTEGRATED_UI_ONE_SHOT_20261110.py'))
    req,adb,sh,rsha,mount_ro,mount_rw,push=(h[k] for k in ['req','adb','sh','rsha','mount_ro','mount_rw','push'])
    sha=lambda b:hashlib.sha256(b).hexdigest()
    out=lab/'build-artifacts/existing-ui-policy-test-20261110'
    req(not out.exists(),'UI policy test already staged')
    req(adb('get-state')=='recovery','tablet not in recovery')
    req(sh('getprop ro.product.device')=='nabu','wrong device')
    req(sh('getprop ro.boot.slot_suffix')=='_b','unexpected boot slot')
    req('uid=0(root)' in sh('id'),'recovery is not root')
    req(int(sh('cat /sys/class/power_supply/battery/capacity'))>=25,'low battery')
    boot=json.loads((lab/'build-artifacts/nabu-boot-b-dbkp-aloha-bootmanager-20261108/FLASHED_BOOT_B.json').read_text())
    req(rsha('/dev/block/by-name/boot_b')==boot['boot_b_sha256'],'automatic UEFI boot chain changed')
    mount_ro()
    menu=h['MENU']; kernel=h['LIVEK']; adt=h['ADT']; data=h['DATA']
    for path,expected in [(menu,h['MENU_OLD_SHA']),(kernel,h['K_OLD_SHA']),(adt,h['ADT_SHA']),(data,h['DATA_SHA'])]:
        req(rsha(path)==expected,'protected live file changed: '+path)
    flags=['offline-legacy-unit-scale=2','nabu-keybag-notifications=1','nabu-aks-state=1','nabu-disable-watchdogd=1','nabu-skip-setup=1','-no_corpses']
    binary=h['OLDK'].read_bytes()
    req(sha(binary)==h['K_OLD_SHA'],'local kernel provenance mismatch')
    for flag in flags[:-1]:
        req(flag.split('=')[0].encode() in binary,'unsupported existing-kernel option: '+flag)
    out.mkdir()
    old=out/'unixnu.before.toml'
    subprocess.run([str(h['ADB']),'-s',h['SER'],'pull',menu,str(old)],check=True,capture_output=True)
    req(sha(old.read_bytes())==h['MENU_OLD_SHA'],'menu backup differs from live')
    text=old.read_text(encoding='utf-8')
    parsed=tomllib.loads(text)
    e=next(x for x in parsed['entry'] if x['id']=='xnu-gpu1g-display-scanout')
    req(e['path']=='Payloads/kernel-fulltrace-panic.macho' and e['initrd']=='Payloads/owner-data-1g-packed.dbr','unexpected existing entry')
    req(parsed['boot']['default']==e['id'],'unexpected old default')
    entry_id='xnu-existing-ui-policy'
    req(all(x['id']!=entry_id for x in parsed['entry']),'test entry already exists')
    for flag in flags:
        req(flag.split('=')[0] not in e['args'],'option already configured: '+flag)
    args=e['args']+' '+' '.join(flags)
    req(len(args.encode('ascii'))<1024,'boot args too long')
    text=text.replace('default = "'+e['id']+'"','default = "'+entry_id+'"',1)
    text+='\n[[entry]]\nid = '+json.dumps(entry_id)+'\ntitle = "iPadOS existing kernel + UI policy test"\ntype = "xnu"\npath = '+json.dumps(e['path'])+'\ninitrd = '+json.dumps(e['initrd'])+'\nargs = '+json.dumps(args)+'\n'
    req(tomllib.loads(text)['boot']['default']==entry_id,'new default invalid')
    new=out/'unixnu.ui-policy.toml'
    new.write_text(text,encoding='utf-8',newline='\n')
    digest=sha(new.read_bytes())
    backup='/esp/EFI/UniXNU/unixnu.pre-ui-policy-test-20261110.toml'
    stage='/tmp/nabu-existing-ui-policy.toml'
    req(not h['rexists'](backup) and not h['rexists'](stage),'staging/backup path exists')
    push(new,stage)
    req(rsha(stage)==digest,'RAM-stage hash mismatch')
    changed=False
    try:
        mount_rw()
        req(rsha(menu)==h['MENU_OLD_SHA'],'live menu changed during staging')
        sh('cp '+menu+' '+backup+'; sync')
        req(rsha(backup)==h['MENU_OLD_SHA'],'on-device menu backup mismatch')
        changed=True
        sh('cp '+stage+' '+menu+'; sync')
        req(rsha(menu)==digest,'menu installation hash mismatch')
    except Exception:
        if changed:
            sh('cp '+backup+' '+menu+'; sync')
            req(rsha(menu)==h['MENU_OLD_SHA'],'menu rollback failed')
        raise
    finally:
        mount_ro()
    req(rsha(menu)==digest,'final read-only menu hash mismatch')
    for path,expected in [(kernel,h['K_OLD_SHA']),(adt,h['ADT_SHA']),(data,h['DATA_SHA'])]:
        req(rsha(path)==expected,'protected payload changed: '+path)
    result={'status':'EXISTING_KERNEL_UI_POLICY_INSTALLED_BOOT_UNVERIFIED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'menu_sha256':digest,'kernel_sha256':h['K_OLD_SHA'],'kernel_replaced':False,'payloads_unchanged':True,'entry':entry_id,'flags':flags,'backup':backup,'boot_verified':False}
    (out/'install-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
