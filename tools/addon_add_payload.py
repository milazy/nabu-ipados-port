#!/usr/bin/env python3
"""Add files to an NGPUADD2 GPU addon and append a trust-cache module with the CDHashes of the new executables.

usage: addon_add_payload.py --addon IN --trustcache IN --out DIR --label TEXT
                            --file NAME=PATH[:MODE] [--file ...]

NAME is the member path below /private/var/ngpu (for example bin/wland, daemons/org.nabu.wland.plist,
wifi/fw/modem/modem.mdt); MODE is octal (0755 for executables, default 0644). Existing members are kept byte for byte
and may not be replaced. Every 0755 member must be an ARM64 Mach-O with a SHA-256 CodeDirectory; its CDHashes are
added to one new trust module unless already trusted. Writes OUT/kernel-fulltrace-panic.macho.gpuaddon and
OUT/kernel-fulltrace-panic.macho.trustcache plus a JSON receipt.
"""
import argparse, hashlib, json, struct, sys, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
from audit_compositor_transport import cdhashes  # noqa: E402


def need(ok, why):
    if not ok:
        raise SystemExit('STOP: ' + why)


def read_addon(data):
    need(data[:8] == b'NGPUADD2', 'not an NGPUADD2 addon')
    count = struct.unpack_from('<I', data, 8)[0]
    at, files = 24, []
    for _ in range(count):
        plen, mode, size, packed = struct.unpack_from('<IIQQ', data, at)
        at += 24
        name = data[at:at + plen - 1].decode()
        at += (plen + 7) & ~7
        body = zlib.decompress(data[at:at + packed])
        need(len(body) == size, 'member size ' + name)
        at += (packed + 7) & ~7
        files.append((name, mode, body))
    need(at == len(data), 'addon length')
    return files


def write_addon(files):
    body = b''
    for name, mode, data in files:
        raw = name.encode() + b'\0'
        packed = zlib.compress(data, 9)
        body += struct.pack('<IIQQ', len(raw), mode, len(data), len(packed))
        body += raw + b'\0' * (-len(raw) % 8) + packed + b'\0' * (-len(packed) % 8)
    return struct.pack('<8sIIQ', b'NGPUADD2', len(files), 0, 24 + len(body)) + body


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--addon', type=Path, required=True)
    p.add_argument('--trustcache', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--label', required=True)
    p.add_argument('--file', action='append', default=[])
    a = p.parse_args()
    old_addon = a.addon.read_bytes()
    files = read_addon(old_addon)
    names = {n for n, _, _ in files}
    new_hashes = set()
    added = []
    for spec in a.file:
        name, _, rest = spec.partition('=')
        path, _, mode = rest.rpartition(':') if rest.count(':') and rest.rsplit(':', 1)[1].isdigit() else (rest, '', '')
        mode = int(mode, 8) if mode else 0o644
        need(name and not name.startswith('/') and '..' not in name.split('/'), 'bad member name ' + name)
        need(name not in names, 'member already in the addon: ' + name)
        data = Path(path).read_bytes()
        need(len(data) <= 64 << 20, 'member too large: ' + name)
        if mode == 0o755:
            need(struct.unpack_from('<I', data)[0] == 0xfeedfacf, 'not a 64-bit Mach-O: ' + name)
            cds = cdhashes(data)
            need(cds and all(cd['hash_type'] == 2 for cd in cds), 'no SHA-256 CodeDirectory: ' + name)
            new_hashes.update(bytes.fromhex(cd['cdhash']) for cd in cds)
        files.append((name, mode, data))
        names.add(name)
        added.append({'name': name, 'mode': oct(mode), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    addon = write_addon(files)
    old = a.trustcache.read_bytes()
    count = struct.unpack_from('<I', old)[0]
    offsets = list(struct.unpack_from('<' + 'I' * count, old, 4)) + [len(old)]
    need(offsets[0] == 4 + 4 * count and offsets == sorted(set(offsets)), 'trust cache bounds')
    modules = [old[s:e] for s, e in zip(offsets, offsets[1:])]
    trusted = set()
    for m in modules:
        version = struct.unpack_from('<I', m)[0]
        n = struct.unpack_from('<I', m, 20)[0]
        stride = {0: 20, 1: 22, 2: 24}[version]
        need(len(m) == 24 + n * stride, 'trust module length')
        trusted.update(m[24 + i * stride:44 + i * stride] for i in range(n))
    missing = sorted(new_hashes - trusted)
    if missing:
        entries = b''.join(cd + bytes((2, 0, 0, 0)) for cd in missing)
        uuid = hashlib.sha256(a.label.encode() + entries).digest()[:16]
        modules.append(struct.pack('<I16sI', 2, uuid, len(missing)) + entries)
    starts, cursor = [], 4 + 4 * len(modules)
    for m in modules:
        starts.append(cursor)
        cursor += len(m)
    cache = struct.pack('<I', len(modules)) + struct.pack('<' + 'I' * len(modules), *starts) + b''.join(modules)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'kernel-fulltrace-panic.macho.gpuaddon').write_bytes(addon)
    (a.out / 'kernel-fulltrace-panic.macho.trustcache').write_bytes(cache)
    receipt = {'label': a.label, 'addon_in': hashlib.sha256(old_addon).hexdigest(),
               'addon_out': hashlib.sha256(addon).hexdigest(), 'trustcache_in': hashlib.sha256(old).hexdigest(),
               'trustcache_out': hashlib.sha256(cache).hexdigest(), 'members': len(files), 'added': added,
               'new_cdhashes': [h.hex() for h in missing]}
    (a.out / 'payload-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    # read back
    need([n for n, _, _ in read_addon(addon)] == [n for n, _, _ in files], 'addon read-back')
    print('ADDON_PAYLOAD_PASS', receipt['addon_out'], receipt['trustcache_out'], 'members', len(files),
          'new_cdhashes', len(missing))


if __name__ == '__main__':
    main()
