#!/usr/bin/env python3
"""Prepare an isolated backlight-v2 trial from a hash-pinned batch-6 readback.

Host only. Firmware already in the baseline addon stays on the owner's PC.
The generated install.sh writes only files below EFI/UniXNU on sda29.
Run via TWRP only after reviewing receipt.json; no flashing or reboot here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from addon_add_payload import read_addon, write_addon

NAME = 'kernel-fulltrace-panic.macho'
PINS = {
    NAME: '3e0a5cc047df13965df204734beb095908387993c7533a95eaffed58a8291c67',
    NAME + '.adt': 'ad6b53b7131900b4764dd6649d6ace425374cc3c06f4fb18cd67f6474fa4e772',
    NAME + '.gpuaddon': '12d95f3b04f41c13b90cb159c4d9927810f13f9ecb1d73bae392cb5dad1dd0ce',
    NAME + '.trustcache': 'b55268b55cbbe6e37411d20785c4838ded2a5c55c3e56ac2e227addce851daf6',
    'unixnu.toml': 'cd660c22cfd0a9185dfd03cc0af75758f878ad28ed09188468e80033aa17b349',
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def menu(raw):
    old = tomllib.loads(raw)
    base = next(e for e in old['entry'] if e['id'] == old['boot']['default'])
    assert base['path'] == 'Payloads/' + NAME
    entries = []
    for ident, title, extra in [
        ('nabu-b7-backlight', 'Batch 7: backlight v2 + icons (experimental)', ['nabu-backlight-v2=1']),
        ('nabu-b7-backlight-off', 'Batch 7: icons, backlight daemon OFF', []),
        ('nabu-b7-appsync', 'Batch 7: backlight v2 + AppSync (experimental)', ['nabu-backlight-v2=1', 'appsync=1']),
    ]:
        e = dict(base, id=ident, title=title, path='Payloads/kernel-batch7.macho')
        e['args'] = ' '.join(a for a in base['args'].split()
                             if not a.startswith(('nabu-backlight=', 'nabu-backlight-v2=', 'appsync=')))
        e['args'] += ' ' + ' '.join(extra)
        entries.append(e)
    # Preserve the complete original menu text and all original entry values.
    marker = 'default = ' + json.dumps(old['boot']['default'])
    assert raw.count(marker) == 1
    new = raw.replace(marker, 'default = "nabu-b7-backlight"', 1)
    for e in entries:
        new += '\n[[entry]]\n' + ''.join(f'{k} = {json.dumps(v)}\n' for k, v in e.items())
    parsed = tomllib.loads(new)
    assert parsed['entry'][:len(old['entry'])] == old['entry']
    assert len({e['id'] for e in parsed['entry']}) == len(parsed['entry'])
    return new


def installer(hashes, required_kib):
    lines = ['#!/sbin/sh', 'set -eu',
             'ESP=/dev/block/sda29', 'M=/tmp/nabu7-install-esp',
             'D=$M/EFI/UniXNU', 'S=/tmp/nabu7-stage',
             'die() { echo "STOP: $*"; exit 1; }',
             'h() { sha256sum "$1" | cut -d" " -f1; }',
             'cleanup() { umount "$M" 2>/dev/null || true; blockdev --setro "$ESP"; }',
             'trap cleanup EXIT',
             '[ "$(getprop ro.product.device)" = nabu ] || die device',
             '[ "$(id -u)" = 0 ] || die root',
             '[ "$(cat /sys/class/power_supply/battery/capacity)" -ge 20 ] || die battery',
             '[ "$(blockdev --getsize64 "$ESP")" = 1073741824 ] || die ESP-size',
             '! grep -q "^$ESP " /proc/mounts || die ESP-already-mounted',
             'mkdir -p "$M"', 'blockdev --setro "$ESP"',
             'mount -t vfat -o ro "$ESP" "$M"']
    for name, digest in PINS.items():
        path = name if name == 'unixnu.toml' else 'Payloads/' + name
        lines.append(f'[ "$(h "$D/{path}")" = {digest} ] || die baseline-{name}')
    lines += ['[ ! -e "$D/unixnu.toml.pre-batch7" ] || die backup-already-exists',
              f'[ "$(df -k "$M" | tail -1 | awk \'{{print $4}}\')" -ge {required_kib} ] || die free-space']
    for name, digest in hashes.items():
        lines.append(f'[ "$(h "$S/{name}")" = {digest} ] || die staging-{name}')
        if name != 'unixnu.toml':
            lines.append(f'[ ! -e "$D/Payloads/{name}" ] || die candidate-already-exists')
    lines += ['echo BATCH7_PREFLIGHT_PASS', 'umount "$M"', 'blockdev --setrw "$ESP"',
              'mount -t vfat -o rw,sync "$ESP" "$M"',
              'cp "$D/unixnu.toml" "$D/unixnu.toml.pre-batch7"', 'sync',
              f'[ "$(h "$D/unixnu.toml.pre-batch7")" = {PINS["unixnu.toml"]} ] || die backup']
    for name in hashes:
        if name != 'unixnu.toml':
            lines.append(f'cp "$S/{name}" "$D/Payloads/{name}"')
    # Prove all new payload files after a readonly remount BEFORE activating the menu.
    lines += ['sync', 'umount "$M"', 'blockdev --setro "$ESP"', 'mount -t vfat -o ro "$ESP" "$M"']
    for name, digest in hashes.items():
        if name != 'unixnu.toml':
            lines.append(f'[ "$(h "$D/Payloads/{name}")" = {digest} ] || die readback-{name}')
    lines += ['umount "$M"', 'blockdev --setrw "$ESP"', 'mount -t vfat -o rw,sync "$ESP" "$M"',
              'cp "$S/unixnu.toml" "$D/unixnu.toml.batch7-new"', 'sync',
              f'[ "$(h "$D/unixnu.toml.batch7-new")" = {hashes["unixnu.toml"]} ] || die new-menu',
              'mv "$D/unixnu.toml.batch7-new" "$D/unixnu.toml"', 'sync', 'umount "$M"',
              'blockdev --setro "$ESP"', 'mount -t vfat -o ro "$ESP" "$M"',
              f'[ "$(h "$D/unixnu.toml")" = {hashes["unixnu.toml"]} ] || die menu-readback']
    for name, digest in PINS.items():
        path = 'unixnu.toml.pre-batch7' if name == 'unixnu.toml' else 'Payloads/' + name
        lines.append(f'[ "$(h "$D/{path}")" = {digest} ] || die fallback-{name}')
    lines += ['umount "$M"', '[ "$(blockdev --getro "$ESP")" = 1 ] || die not-readonly',
              'echo BATCH7_INSTALL_READBACK_PASS']
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--backlight', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    for name, digest in PINS.items():
        if sha(a.baseline / name) != digest:
            raise SystemExit('Baseline mismatch: ' + name)
    if b'NABU_BACKLIGHT_V2' not in a.backlight.read_bytes():
        raise SystemExit('Wrong backlight executable')
    a.out.mkdir(exist_ok=False, parents=True)
    original = read_addon((a.baseline / (NAME + '.gpuaddon')).read_bytes())
    kept = [x for x in original if x[0] != 'bin/nabu-backlight']
    assert len(kept) == len(original) - 1
    stripped = a.out / 'base.gpuaddon'
    stripped.write_bytes(write_addon(kept))
    subprocess.run([sys.executable, str(ROOT / 'tools/addon_add_payload.py'),
                    '--addon', str(stripped), '--trustcache', str(a.baseline / (NAME + '.trustcache')),
                    '--out', str(a.out / 'built'), '--label', 'nabu-batch7-backlight-v2',
                    '--file', f'bin/nabu-backlight={a.backlight}:0755'], check=True)
    stage = a.out / 'stage'
    stage.mkdir()
    for suffix in ('', '.adt', '.gpuaddon', '.trustcache'):
        source = a.baseline if suffix in ('', '.adt') else a.out / 'built'
        shutil.copyfile(source / (NAME + suffix), stage / ('kernel-batch7.macho' + suffix))
    rebuilt = read_addon((stage / 'kernel-batch7.macho.gpuaddon').read_bytes())
    assert [x for x in rebuilt if x[0] != 'bin/nabu-backlight'] == kept
    (stage / 'unixnu.toml').write_text(menu((a.baseline / 'unixnu.toml').read_text()), encoding='utf-8', newline='\n')
    hashes = {f.name: sha(f) for f in sorted(stage.iterdir())}
    required_kib = sum(f.stat().st_size for f in stage.iterdir()) // 1024 + 32768
    (a.out / 'install.sh').write_text(installer(hashes, required_kib), encoding='utf-8', newline='\n')
    receipt = dict(status='PREPARED_NOT_INSTALLED', baseline=PINS, candidate=hashes,
                   backlight_sha256=sha(a.backlight), minimum_free_kib=required_kib,
                   changed_addon_members=['bin/nabu-backlight'],
                   recovery='Select original xnu-existing-ui-policy; original payload files are unchanged. '
                            'The replaced menu is backed up as unixnu.toml.pre-batch7.')
    (a.out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
