#!/usr/bin/env python3
"""One bounded recovery/log retrieval; no persistent flash or automatic XNU retry."""
import argparse,datetime,hashlib,json,re,subprocess,sys,time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--serial',required=True)
    p.add_argument('--wait-seconds',type=int,default=600)
    a=p.parse_args();root=a.root.resolve()
    if not 0<=a.wait_seconds<=900:raise ValueError('Wait budget out of range')
    adb=root/'platform-tools/adb.exe';fb=root/'platform-tools/fastboot.exe'
    image=root/'boot-preflight/V4-MODDED-TWRP-LINUX.img'
    if hashlib.file_digest(image.open('rb'),'sha256').hexdigest()!='7a71da691a9117cf959ced0557593d647a8fc384b2374404f14184126ab7cbc6':raise ValueError('Recovery image changed')
    expected=json.loads((root/'build-artifacts/nabu-standard-compositor-20261110/install-receipt.json').read_text())
    if expected['status']!='STANDARD_COMPOSITOR_INSTALL_PASS_BOOT_UNVERIFIED':raise ValueError('Installation identity missing')
    def run(exe,args,timeout=20,check=True):
        r=subprocess.run([str(exe),'-s',a.serial,*args],capture_output=True,timeout=timeout)
        if check and r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-350:])
        return r
    deadline=time.monotonic()+a.wait_seconds;booted=False;announced=False
    while True:
        state=run(adb,['get-state'],check=False).stdout.decode(errors='replace').strip()
        if state=='recovery':break
        devices=subprocess.run([str(fb),'devices'],capture_output=True,timeout=10).stdout.decode(errors='replace')
        if a.serial in [line.split()[0] for line in devices.splitlines() if line.split()] and not booted:
            product=run(fb,['getvar','product']).stderr.decode(errors='replace')
            if not re.search(r'product:\s*nabu\b',product):raise ValueError('Wrong Fastboot product')
            run(fb,['boot',str(image)],timeout=60);booted=True
            print('TEMPORARY_RECOVERY_BOOT_ACCEPTED',flush=True)
        if time.monotonic()>=deadline:raise TimeoutError('No reachable recovery within this bounded session; no persistent flash performed')
        if not announced:print('WAITING_FOR_RECOVERY_OR_FASTBOOT; no device changes until an identified connection appears',flush=True);announced=True
        time.sleep(3)
    def sh(s):return run(adb,['shell',s],timeout=90).stdout.decode(errors='replace').strip()
    if sh('getprop ro.product.device')!='nabu' or 'uid=0(root)' not in sh('id'):raise ValueError('Wrong recovery device or privileges')
    esp='/dev/block/sda29'
    if sh('blockdev --getsize64 '+esp)!='1073741824':raise ValueError('Unexpected ESP')
    sh('sync; umount /esp 2>/dev/null || true; blockdev --setro '+esp)
    if sh('blockdev --getro '+esp)!='1':raise ValueError('ESP block readonly failed')
    sh('mkdir -p /esp; mount -t vfat -o ro '+esp+' /esp')
    if ' ro,' not in sh("cat /proc/mounts | grep ' /esp '"):raise ValueError('Read-only mount failed')
    k='/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
    for remote,key in ((k,'kernel_sha256'),(k+'.trustcache','trustcache_sha256'),('/esp/EFI/UniXNU/unixnu.toml','menu_sha256')):
        if sh('sha256sum '+remote).split()[0]!=expected[key]:raise ValueError('Installed identity changed: '+key)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=root/'reports'/('standard-compositor-'+stamp);out.mkdir(exist_ok=False)
    raw=out/'boot-log.bin';run(adb,['pull','/esp/XNU2LOG.BIN',str(raw)],timeout=150)
    sys.path.insert(0,str(root/'UniXNU-nabu/tools'))
    from nabu_log_volume import decode_container
    payload,info=decode_container(raw.read_bytes());text=payload.decode('utf-8',errors='replace')
    (out/'boot-log.txt').write_text(text,encoding='utf-8')
    args=next((line for line in text.splitlines() if 'boot-args = ' in line),'')
    binding=all(flag in args.split() for flag in ('sheng-gpu-addon=1','nabu-ui-watch=1','sheng-vsync=60'))
    lines=[line for line in text.splitlines() if re.search(r'NABU ADDON|NabuUI:|NABU DISPLAY|NABU EXIT|NABU.*EXCEPTION|panic\(cpu|Process\[|Library not loaded|AMFI.*(deny|reject|killed)',line)]
    report={'status':'CRC_VERIFIED_RECOVERY_READBACK_UI_NOT_PROVEN','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_sha256':hashlib.file_digest(raw.open('rb'),'sha256').hexdigest(),'container':info,'installed_kernel_sha256':expected['kernel_sha256'],'selected_boot_arguments_match':binding,'kernel_version':text.splitlines()[0] if text else '', 'focused_lines':len(lines),'boot_proven':False,'ESP_readonly_after':sh('blockdev --getro '+esp)=='1'}
    (out/'readback.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'focused.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('CRC_VERIFIED_READBACK',out,flush=True)
    print('BINDING_FLAGS_MATCH',binding,'BOOT_ID',info.get('boot_id'),'SEQUENCE',info.get('sequence'),flush=True)
    print('\n'.join(lines[-65:]),flush=True)
if __name__=='__main__':main()
