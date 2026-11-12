#!/usr/bin/env python3
"""NABU_LAUNCHD_CACHE_V1: let owner launchd jobs actually start on iPadOS 17 (boot-arg nabu-launchd-cache=1).

Batch-3 evidence: the addon wrote daemons/org.nabu.wland.plist and the daemons union mount reached stage 5, yet wland
never logged. iOS 17 launchd reads system jobs only from its verified cache /System/Library/xpc/launchd.plist(.sig); a
plist dropped into /System/Library/LaunchDaemons is ignored. UniXNU nabu's userprobe mode (scripts/nabu_gpu_userprobe_source.py)
shows the working arrangement, which this reuses in the standard addon path:
  /private/var/ngpu/bin   -> /usr/bin            (xpcproxy may only exec regular files outside /private/var)
  /private/var/ngpu/cache -> /System/Library/xpc  (owner-merged launchd.plist + detached ad-hoc signature, CDHash in trust)
Edits patches/xnu/zzy-native-gpu-addon-mount.patch of the UniXNU tree (after ci/nabu-standard-addon-diagnostics.patch).
The cache mount happens only when both cache files exist; without the boot-arg nothing changes. Scratch 0xa00..0xb20 sits below
mkdir's 0xc00; 0x400 is reused after the extensions mount finished with it.
"""
import argparse, re
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tree', type=Path, required=True)
a = p.parse_args()
f = a.tree / 'patches/xnu/zzy-native-gpu-addon-mount.patch'
s = f.read_text()
if 'NABU_LAUNCHD_CACHE_V1' in s:
    raise SystemExit('already applied')
# Before the wallpaper mount: zzy-staged-system-apps.patch uses the wallpaper mount's end and the closing brace as context.
anchor = "+	/* The default iPadOS 17 wallpaper's layered animation with PNG images in place of its HEIC ones (no hardware HEVC decoder here).\n"
if s.count(anchor) != 1:
    raise SystemExit('anchor drift: wallpaper comment (count %d)' % s.count(anchor))
code = r'''	/* NABU_LAUNCHD_CACHE_V1 (ci/apply_launchd_cache_mount.py): owner jobs through launchd's verified cache. */
	uint32_t nabu_launchd_cache = 0;
	if (PE_parse_boot_argn("nabu-launchd-cache", &nabu_launchd_cache, sizeof(nabu_launchd_cache)) &&
	    (nabu_launchd_cache == 1 || nabu_launchd_cache == 2)) {
		static volatile int nabu_bin_stage = 0, nabu_bin_status = -1, nabu_cache_stage = 0, nabu_cache_status = -1;
		static const char bin_source[] = "/private/var/ngpu/bin", bin_point[] = "/usr/bin";
		native_gpu_addon_mount(p, scratch, 0xa00, bin_source, sizeof(bin_source), bin_point, sizeof(bin_point),
		    "/usr/bin/IOMFB_FDR_Loader", "/usr/bin/wland", &nabu_bin_stage, &nabu_bin_status);
		vnode_t nabu_probe = NULLVP;
		int nabu_have = 0;
		/* 1: cache/ (with the iconservicesagent CoreImage override), 2: cache-plain/ (owner jobs only). */
		const int nabu_plain = nabu_launchd_cache == 2;
		if (!vnode_lookup(nabu_plain ? "/private/var/ngpu/cache-plain/launchd.plist" : "/private/var/ngpu/cache/launchd.plist",
		    0, &nabu_probe, vfs_context_current())) {
			vnode_put(nabu_probe);
			nabu_probe = NULLVP;
			if (!vnode_lookup(nabu_plain ? "/private/var/ngpu/cache-plain/launchd.plist.sig" :
			    "/private/var/ngpu/cache/launchd.plist.sig", 0, &nabu_probe, vfs_context_current())) {
				vnode_put(nabu_probe);
				nabu_have = 1;
			}
		}
		/* bin stage >= 3: the union mount itself succeeded (4/5 only add visibility checks). */
		if (nabu_have && nabu_bin_stage >= 3) {
			static const char cache_source[] = "/private/var/ngpu/cache", plain_source[] = "/private/var/ngpu/cache-plain",
			    cache_point[] = "/System/Library/xpc";
			native_gpu_addon_mount(p, scratch, 0x400, nabu_plain ? plain_source : cache_source,
			    nabu_plain ? sizeof(plain_source) : sizeof(cache_source), cache_point, sizeof(cache_point),
			    "/System/Library/xpc/foreground_user_endpoints.plist", "/System/Library/xpc/launchd.plist.sig",
			    &nabu_cache_stage, &nabu_cache_status);
		}
		printf("NABU LAUNCHD cache mode=%u have=%d bin=%d/%d cache=%d/%d\n", nabu_launchd_cache, nabu_have, nabu_bin_stage, nabu_bin_status,
		    nabu_cache_stage, nabu_cache_status);
	}
'''
lines = ['+' + l for l in code.splitlines()]
insert = '\n'.join(lines) + '\n'
s = s.replace(anchor, insert + anchor, 1)
# Fix the kern_exec.c hunk header (the hunk that holds the anchor is the first new-file hunk of kern_exec.c).
m = re.search(r'@@ -7193,6 \+7193,(\d+) @@', s)
if not m:
    raise SystemExit('hunk header drift')
s = s[:m.start(1)] + str(int(m[1]) + len(lines)) + s[m.end(1):]
f.write_text(s)
print('NABU_LAUNCHD_CACHE_V1 applied, +%d lines' % len(lines))
