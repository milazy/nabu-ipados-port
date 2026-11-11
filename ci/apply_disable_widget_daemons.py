"""Disable chronod and liveactivitiesd through launchd's override database on nabu's RAM Data volume.

Hardware evidence (XNU2LOG seq 2419, after the AppleKeyStore key-wrap fix, where aks_wrap_key now
succeeds): SpringBoard's main thread still waits from sample 29 to the end in a synchronous XPC reply
from chronod (com.apple.chronoservices, from -[SBHIconManager init]). chronod's main thread waits in a
synchronous BoardServices call from ActivityKit; liveactivitiesd's main thread waits in a synchronous
-[_CDClientContext objectForContextualKeyPath:] (contextstored) and its IDS thread in
IDSCopyLocalDeviceUniqueID. None of these return while the boot is observed, so SpringBoard never
completes startup and the render server never gets a frame.

With both jobs disabled, launchd does not register their Mach services: SpringBoard's lookup of
com.apple.chronoservices fails at once (XPC_ERROR_CONNECTION_INVALID) instead of waiting forever, and
startup continues without widgets and Live Activities. Labels read from the 21H16 IPSW:
/System/Library/LaunchDaemons/com.apple.chronod.plist, com.apple.liveactivitiesd.plist.

The override file already exists for nabu-disable-watchdogd=1 (UniXNU sheng-disable-watchdogd); this
adds two keys to the same root-owned plist, under the same boot argument.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
f = a.source / 'source-ci/nabu_data_skeleton.py'
s = f.read_text()
old = "WATCHDOGD_DISABLED = plistlib.dumps({'com.apple.watchdogd': True})"
if s.count(old) != 1:
    raise SystemExit('anchor drift: WATCHDOGD_DISABLED (count %d)' % s.count(old))
s = s.replace(old, "# NABU_DISABLE_WIDGET_DAEMONS_V1: chronod/liveactivitiesd never answer on nabu (seq 2419).\n"
              "WATCHDOGD_DISABLED = plistlib.dumps({'com.apple.watchdogd': True, 'com.apple.chronod': True,\n"
              "                                     'com.apple.liveactivitiesd': True})", 1)
old_msg = 'printf("NABU DATA: launchd override disables com.apple.watchdogd\\n");'
if s.count(old_msg) != 1:
    raise SystemExit('anchor drift: override message (count %d)' % s.count(old_msg))
s = s.replace(old_msg, 'printf("NABU DATA: launchd override disables watchdogd chronod liveactivitiesd\\n");', 1)
f.write_text(s)
print('NABU_DISABLE_WIDGET_DAEMONS_PATCH_PASS', f)
