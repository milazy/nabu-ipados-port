#!/usr/bin/env python3
"""Update the guarded installer baseline to the verified existing-kernel UI menu."""
from pathlib import Path
import argparse,hashlib,json
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--lab',type=Path,required=True)
a=p.parse_args()
lab=a.lab.resolve()
src=lab/'INSTALL_INTEGRATED_UI_ONE_SHOT_20261110.py'
out=lab/'build-artifacts/nabu-integrated-ui-final-20261110'
backup=out/'INSTALL.before-ui-policy-rebase.py'
receipt=json.loads((lab/'build-artifacts/existing-ui-policy-test-20261110/install-receipt.json').read_text())
assert receipt['status']=='EXISTING_KERNEL_UI_POLICY_INSTALLED_BOOT_UNVERIFIED'
base='build-artifacts/existing-ui-policy-test-20261110/unixnu.ui-policy.toml'
digest=hashlib.sha256((lab/base).read_bytes()).hexdigest()
assert digest==receipt['menu_sha256']
s=src.read_text()
original=s
def once(old,new):
    global s
    assert s.count(old)==1,repr(old)
    s=s.replace(old,new,1)
once('BASE=R/"build-artifacts/nabu-oneboot-data1g-gpufix-20261109/unixnu.gpu1g-legacy-display-present-ready.toml"','BASE=R/"'+base+'"')
once('MENU_OLD_SHA="febb97a8c15a360e1ff14f127f788fd9b6240087c9f14fed3e42a6c750a7f7b1"','MENU_OLD_SHA="'+digest+'"')
token='"xnu-gpu1g-display-scanout"'
assert s.count(token)==5,s.count(token)
s=s.replace(token,'"xnu-existing-ui-policy"')
once('iPadOS GPU+1GiB DISPLAY SCANOUT (UNVERIFIED)','iPadOS existing kernel + UI policy test')
once(' offline-legacy-unit-scale=2 sheng-vsync=60 nabu-keybag-notifications=1 nabu-aks-state=1 nabu-disable-watchdogd=1 nabu-skip-setup=1 nabu-gpu-scanout=1 nabu-cpu-diff=0 -no_corpses',' sheng-vsync=60 nabu-gpu-scanout=1 nabu-cpu-diff=0')
compile(s,str(src),'exec')
assert not backup.exists()
backup.write_text(original,newline='\n')
src.write_text(s,newline='\n')
print('INTEGRATED_INSTALLER_REBASED_TO_VERIFIED_UI_MENU',digest)
