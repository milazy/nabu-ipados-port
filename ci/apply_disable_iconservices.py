"""nabu-disable-watchdogd=2: also disable iconservicesagent through launchd's override database.

Hardware evidence (XNU2LOG seq 3328): iconservicesagent crashes 14 times, always SIGSEGV at pc=0 with
lr = CoreImage CI::GLContext::init() + 220 (21H16 dyld cache 0x1976eeac4): the OpenGL ES dispatch table filled
by GetMacroContext is empty on nabu, so the first GL entry (glDisable(GL_DEPTH_TEST), 0xb71) is a NULL call.
Settings (com.apple.Preferences) then never draws and is killed with 0x8BADF00D.

UniXNU sheng records the same chain (porting.toml, lite=2, boot 50d4021e7): with
com.apple.iconservices.iconservicesagent disabled, Settings opened; app icon artwork was missing.

Gating keeps the old behaviour: nabu-disable-watchdogd=1 writes the same disabled.plist as before;
nabu-disable-watchdogd=2 writes the plist with iconservicesagent added (one file, same path, same owner/mode).
Applied after ci/apply_disable_widget_daemons.py.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
f = a.source / 'source-ci/nabu_data_skeleton.py'
s = f.read_text()


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: %s (count %d)' % (what, text.count(old)))
    return text.replace(old, new, 1)


s = once(s, "LAUNCHD_FILES = (\n",
         "# NABU_DISABLE_ICONSERVICES_V1: CoreImage's empty GL dispatch crashes iconservicesagent (seq 3328).\n"
         "ICONSERVICES_DISABLED = plistlib.dumps({**plistlib.loads(WATCHDOGD_DISABLED),\n"
         "                                        'com.apple.iconservices.iconservicesagent': True})\n"
         "LAUNCHD_FILES = (\n", 'LAUNCHD_FILES')
s = once(s, "    seeded = [('watchdogd', path, content, 0o644, 0, 0) for path, content in LAUNCHD_FILES]\n",
         "    seeded = [('xwatchdogd' if path.endswith('disabled.plist') else 'watchdogd', path, content, 0o644, 0, 0)\n"
         "              for path, content in LAUNCHD_FILES]\n"
         "    seeded += [('vicons', 'db/com.apple.xpc.launchd/disabled.plist', ICONSERVICES_DISABLED, 0o644, 0, 0)]\n",
         'seeded launchd files')
s = once(s, "\t\tunsigned enabled = files[i].gate[0] == 'w' ? disable_watchdogd :\n",
         "\t\tunsigned enabled = files[i].gate[0] == 'w' ? (disable_watchdogd == 1 || disable_watchdogd == 2) :\n"
         "\t\t    files[i].gate[0] == 'x' ? (disable_watchdogd == 1) :\n"
         "\t\t    files[i].gate[0] == 'v' ? (disable_watchdogd == 2) :\n", 'gate loop')
s = once(s, '\tif (disable_watchdogd == 1) printf("NABU DATA: launchd override disables watchdogd chronod liveactivitiesd\\n");',
         '\tif (disable_watchdogd == 1) printf("NABU DATA: launchd override disables watchdogd chronod liveactivitiesd\\n");\n'
         '\tif (disable_watchdogd == 2) printf("NABU DATA: launchd override disables watchdogd chronod liveactivitiesd iconservicesagent\\n");',
         'message')
f.write_text(s)
print('NABU_DISABLE_ICONSERVICES_V1 applied', f)
