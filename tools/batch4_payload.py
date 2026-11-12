#!/usr/bin/env python3
"""Assemble the batch-4 addon member list for tools/addon_add_payload.py (PC side).

usage: batch4_payload.py --cache-art DIR --firmware DIR [--wlan-conf FILE] [--ipa-dir DIR] --out ARGS.json

DIR is the downloaded nabu-launchd-cache artifact (out/ and appsync-out/). Writes a JSON list of
"NAME=PATH[:MODE]" member specs plus the launchd cache CDHashes to trust. Members:
  bin/wland, bin/netsvc, bin/nabu-ipa-autoinstall            (/usr/bin union, 0755)
  cache/launchd.plist(.sig)        wland + IPA job + iconservicesagent CoreImage override (nabu-launchd-cache=1)
  cache-plain/launchd.plist(.sig)  wland only (nabu-launchd-cache=2)
  appsync/{lib,libexec,helper,coreservices}/...   AppSync 21H16 runtime (used only with appsync=1)
  wifi/fw/..., wifi/wlan.conf (0600, PC only), ipa/*.ipa
Firmware and wlan.conf never leave the PC except onto the tablet.
"""
import argparse, json
from pathlib import Path

MACHO = (b'\xcf\xfa\xed\xfe',)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cache-art', type=Path, required=True)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--wlan-conf', type=Path)
    p.add_argument('--ipa-dir', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out, aso = a.cache_art / 'out', a.cache_art / 'appsync-out'
    files = [f'bin/wland={out / "wland"}:0755', f'bin/netsvc={out / "netsvc"}:0755',
             f'bin/nabu-ipa-autoinstall={aso / "nabu-ipa-autoinstall"}:0755']
    caches = {'cache': out / 'cache-iconfix-appsync', 'cache-plain': out / 'cache-plain'}
    cdhashes = []
    for member, folder in caches.items():
        files += [f'{member}/launchd.plist={folder / "launchd.plist"}', f'{member}/launchd.plist.sig={folder / "launchd.plist.sig"}']
        report = json.loads((folder / 'launchd-cache.json').read_text())
        cdhashes.append(report['cdhash'])
    root = aso / 'appsync'
    count = 0
    for top in ('lib', 'libexec', 'helper', 'coreservices'):
        for path in sorted((root / top).rglob('*')):
            if not path.is_file():
                continue
            name = 'appsync/' + path.relative_to(root).as_posix()
            if len(name) >= 160:
                raise SystemExit('member name too long: ' + name)
            with path.open('rb') as f:
                exe = f.read(4) in MACHO
            files.append(f'{name}={path}' + (':0755' if exe else ''))
            count += 1
    for path in sorted((a.firmware / 'modem').iterdir()):
        if path.is_file():
            files.append(f'wifi/fw/modem/{path.name}={path}')
    for n in ('modemst1', 'modemst2', 'fsg', 'fsc'):
        files.append(f'wifi/fw/rmtfs/{n}.img={a.firmware / "efs" / (n + ".bin")}')
    if a.wlan_conf and a.wlan_conf.is_file():
        files.append(f'wifi/wlan.conf={a.wlan_conf}:0600')
    ipas = []
    if a.ipa_dir and a.ipa_dir.is_dir():
        for path in sorted(a.ipa_dir.glob('*.ipa')):
            files.append(f'ipa/{path.name}={path}')
            ipas.append(path.name)
    a.out.write_text(json.dumps({'files': files, 'cdhashes': cdhashes}, indent=1) + '\n')
    print('BATCH4_MEMBERS', len(files), 'appsync', count, 'cdhashes', ' '.join(cdhashes),
          'wlan.conf', 'yes' if a.wlan_conf and a.wlan_conf.is_file() else 'no', 'ipas', len(ipas))


if __name__ == '__main__':
    main()
