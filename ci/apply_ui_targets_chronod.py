"""Add chronod, liveactivitiesd and lsd to the nabu UI watch and its user-stack sampler.

Hardware evidence (XNU2LOG seq 2128, stacks symbolized against the 21H16 dyld cache):
SpringBoard's main thread waits from sample 23 to the end of capture in
xpc_connection_send_message_with_reply_sync <- BSXPCServiceConnectionMessage <-
-[CHSChronoServicesConnection _subscribeToExtensions] <- -[CHSWidgetExtensionProvider
registerObserver:] <- -[SBHIconManager init] <- -[SBUIController init] <-
-[SpringBoard _completeStartupAfterMainSceneConnect:]. chronod never answers, so SpringBoard never
finishes startup and backboardd never receives a frame (swaps 0). UniXNU's venus record describes the
same chain (liveactivitiesd -> chronod -> SpringBoard). Samples 11-19 showed SpringBoard waiting on the
LaunchServices context lock, so lsd is sampled too.

Changes (diagnostic only, applied after apply_ui_stack_sampler.py):
- NABU_UI_TARGETS 3 -> 6: chronod, liveactivitiesd, lsd are watched like the first three.
- Exec-path matching compares the path's last component with the target name, so the watch does not
  depend on each daemon's install path.
- The stack sampler runs for every target except runningboardd.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
gen = a.source / 'scripts/nabu_ui_watch_source.py'
s = gen.read_text()


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: ' + what + ' (count %d)' % text.count(old))
    return text.replace(old, new, 1)


if 'NABU_UI_TARGETS_V2' in s:
    raise SystemExit('targets already extended')
if 'NABU_UI_STACK_V1' not in s:
    raise SystemExit('apply_ui_stack_sampler.py must run first')

s = once(s, 'enum { NABU_UI_TARGETS = 3, NABU_UI_MAX_EVENTS = 96, NABU_UI_MAX_SAMPLES = 64 };',
         '/* NABU_UI_TARGETS_V2: chronod, liveactivitiesd, lsd added. */\n'
         'enum { NABU_UI_TARGETS = 6, NABU_UI_MAX_EVENTS = 192, NABU_UI_MAX_SAMPLES = 64 };',
         'targets enum')
s = once(s, '''    "SpringBoard", "backboardd", "runningboardd"
};''', '''    "SpringBoard", "backboardd", "runningboardd", "chronod", "liveactivitiesd", "lsd"
};''', 'names')
s = once(s, '''    "/usr/libexec/backboardd", "/usr/libexec/runningboardd"
};''', '''    "/usr/libexec/backboardd", "/usr/libexec/runningboardd", "chronod", "liveactivitiesd", "lsd"
};''', 'paths')
s = once(s, '''    for (unsigned i = 0; i < NABU_UI_TARGETS; ++i) {
        if (!strcmp(name, path ? nabu_ui_paths[i] : nabu_ui_names[i])) return (int)i;
    }''', '''    const char *base = name;
    if (path) {
        for (const char *c = name; *c; ++c) if (*c == '/') base = c + 1;
    }
    for (unsigned i = 0; i < NABU_UI_TARGETS; ++i) {
        if (!strcmp(name, path ? nabu_ui_paths[i] : nabu_ui_names[i])) return (int)i;
        if (path && !strcmp(base, nabu_ui_names[i])) return (int)i;
    }''', 'target match')
s = once(s, 'if (thread && !exited && i < 2 && (sample & 1) && sample <= 40)',
         'if (thread && !exited && i != 2 && (sample & 1) && sample <= 40)', 'sampler targets')
gen.write_text(s)
print('NABU_UI_TARGETS_CHRONOD_PATCH_PASS', gen)
