#!/usr/bin/env python3
"""NABU_APPSYNC_RUNTIME_V1: AppSync's owner-signed copies at the original service paths (boot-arg appsync=1).

Port of UniXNU sheng-appsync-runtime.patch (xnu-12377) into this tree's standard addon path. Applied after
ci/apply_launchd_cache_mount.py (it anchors on that block's closing printf). The kernel half of AppSync is
ci/zzzz-nabu-appsync-user-trust.patch. Mounts (read-only unions, sources written from the GPU addon):
  /private/var/ngpu/appsync/lib          -> /usr/lib   (UniXNUAppSync.dylib, libunixnu-ldid.dylib)
  /private/var/ngpu/appsync/libexec      -> /usr/libexec   (installd, backboardd, unixnu-appinst)
  /private/var/ngpu/appsync/helper       -> MobileInstallationHelperService.xpc
  /private/var/ngpu/appsync/coreservices -> /System/Library/CoreServices   (SpringBoard.app copy)
The library mount comes first so a missing library can never hide a system executable.
"""
import argparse, re
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tree', type=Path, required=True)
a = p.parse_args()
f = a.tree / 'patches/xnu/zzy-native-gpu-addon-mount.patch'
s = f.read_text()
if 'NABU_APPSYNC_RUNTIME_V1' in s:
    raise SystemExit('already applied')
anchor = ('+		    nabu_bin_stage, nabu_bin_status, nabu_cache_stage, nabu_cache_status, nabu_lib_stage, nabu_lib_status);\n'
          '+	}\n')
if s.count(anchor) != 1:
    raise SystemExit('anchor drift: launchd cache block (count %d)' % s.count(anchor))
code = r'''	/* NABU_APPSYNC_RUNTIME_V1 (ci/apply_appsync_runtime_mount.py) */
	uint32_t appsync_enabled = 0;
	if (PE_parse_boot_argn("appsync", &appsync_enabled, sizeof(appsync_enabled)) && appsync_enabled == 1) {
		static const char as_lib_source[] = "/private/var/ngpu/appsync/lib", as_lib_point[] = "/usr/lib";
		static volatile int as_lib_stage, as_lib_status;
		native_gpu_addon_mount(p, scratch, 0x600, as_lib_source, sizeof(as_lib_source),
		    as_lib_point, sizeof(as_lib_point), "/usr/lib/dyld", "/usr/lib/UniXNUAppSync.dylib",
		    &as_lib_stage, &as_lib_status);
		if (as_lib_stage == 5 && !as_lib_status) {
			static const char as_exec_source[] = "/private/var/ngpu/appsync/libexec", as_exec_point[] = "/usr/libexec";
			static const char as_helper_source[] = "/private/var/ngpu/appsync/helper";
			static const char as_helper_point[] = "/System/Library/PrivateFrameworks/MobileInstallation.framework/XPCServices/"
			    "com.apple.MobileInstallationHelperService.xpc";
			/* Above SpringBoard.app, not on it: LaunchServices refuses a mount root as a bundle. */
			static const char as_sb_source[] = "/private/var/ngpu/appsync/coreservices";
			static const char as_sb_point[] = "/System/Library/CoreServices";
			static volatile int as_exec_stage, as_exec_status, as_helper_stage, as_helper_status, as_sb_stage, as_sb_status;
			native_gpu_addon_mount(p, scratch, 0x600, as_exec_source, sizeof(as_exec_source),
			    as_exec_point, sizeof(as_exec_point), "/usr/libexec/launchd_cache_loader", "/usr/libexec/unixnu-appinst",
			    &as_exec_stage, &as_exec_status);
			native_gpu_addon_mount(p, scratch, 0x600, as_helper_source, sizeof(as_helper_source),
			    as_helper_point, sizeof(as_helper_point),
			    "/System/Library/PrivateFrameworks/MobileInstallation.framework/XPCServices/"
			    "com.apple.MobileInstallationHelperService.xpc/Info.plist",
			    "/System/Library/PrivateFrameworks/MobileInstallation.framework/XPCServices/"
			    "com.apple.MobileInstallationHelperService.xpc/UniXNUAppSync.runtime", &as_helper_stage, &as_helper_status);
			native_gpu_addon_mount(p, scratch, 0x600, as_sb_source, sizeof(as_sb_source),
			    as_sb_point, sizeof(as_sb_point), "/System/Library/CoreServices/SystemVersion.plist",
			    "/System/Library/CoreServices/SpringBoard.app/UniXNUAppSync.runtime", &as_sb_stage, &as_sb_status);
			printf("NABU APPSYNC installd=%d/%d helper=%d/%d SpringBoard=%d/%d\n",
			    as_exec_stage, as_exec_status, as_helper_stage, as_helper_status, as_sb_stage, as_sb_status);
		}
		printf("NABU APPSYNC library=%d/%d\n", as_lib_stage, as_lib_status);
	}
'''
lines = ['+' + l for l in code.splitlines()]
s = s.replace(anchor, anchor + '\n'.join(lines) + '\n', 1)
m = re.search(r'@@ -7193,6 \+7193,(\d+) @@', s)
if not m:
    raise SystemExit('hunk header drift')
s = s[:m.start(1)] + str(int(m[1]) + len(lines)) + s[m.end(1):]
f.write_text(s)
print('NABU_APPSYNC_RUNTIME_V1 applied, +%d lines' % len(lines))
