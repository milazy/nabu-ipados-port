#!/usr/bin/env python3
"""Add addons/NativeAdrenoMetal.clients to an NGPUADD2 GPU addon, leaving every existing member byte-identical.

The Adreno Metal plugin gives a process other than backboardd its own Metal device only when the process name is listed in
NativeAdrenoMetal.clients beside the bundle (adrenometal NativeAdrenoMetalPlugin.mm listedClient(); the kernel's sheng-gpu-addon
install writes every addon member to /private/var/ngpu/<name> and union-mounts /private/var/ngpu/addons over
/System/Library/Extensions). UniXNU evb10 record: taps on Settings did not open the app because iconservicesagent and Preferences had
no Metal device; sirius record: iconservicesagent crashes in CoreImage (CI::GLContext::init) without one. nabu seq 3164 shows
iconservicesagent crashing 11 times and Settings never starting.

The clients file is data (mode 0644), so the paired trust cache is unchanged.

usage: addon_add_clients.py IN.gpuaddon OUT.gpuaddon NAME [NAME ...]
"""
import hashlib, struct, sys, zlib

CLIENTS = 'addons/NativeAdrenoMetal.clients'


def entries(b):
    if b[:8] != b'NGPUADD2':
        sys.exit('STOP: not an NGPUADD2 addon')
    count, reserved, total = struct.unpack_from('<IIQ', b, 8)
    if reserved or total != len(b):
        sys.exit('STOP: addon header')
    at, out = 24, []
    for _ in range(count):
        nb, mode, size, packed = struct.unpack_from('<IIQQ', b, at)
        start = at
        at += 24
        name = b[at:at + nb - 1].decode()
        at += (nb + 7) & ~7
        data = zlib.decompress(b[at:at + packed])
        if len(data) != size:
            sys.exit('STOP: member size ' + name)
        at += (packed + 7) & ~7
        out.append((name, mode, data, b[start:at]))
    if at != len(b):
        sys.exit('STOP: trailing data')
    return out


def member(name, mode, data):
    raw = name.encode() + b'\0'
    packed = zlib.compress(data, 9)
    return (struct.pack('<IIQQ', len(raw), mode, len(data), len(packed)) + raw + b'\0' * ((-len(raw)) % 8) +
            packed + b'\0' * ((-len(packed)) % 8))


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    for n in names:
        if not n.replace('.', '').replace('-', '').replace('_', '').isalnum() or len(n) > 64:
            sys.exit('STOP: bad process name ' + n)
    old = open(src, 'rb').read()
    items = [e for e in entries(old) if e[0] != CLIENTS]
    text = ('\n'.join(names) + '\n').encode()
    body = b''.join(e[3] for e in items) + member(CLIENTS, 0o644, text)
    new = struct.pack('<8sIIQ', b'NGPUADD2', len(items) + 1, 0, 24 + len(body)) + body
    check = entries(new)
    for (a, b) in zip(items, check):
        if a[0] != b[0] or a[1] != b[1] or a[2] != b[2]:
            sys.exit('STOP: existing member changed: ' + a[0])
    if check[-1][0] != CLIENTS or check[-1][2] != text:
        sys.exit('STOP: clients member')
    open(dst, 'wb').write(new)
    print('in ', hashlib.sha256(old).hexdigest(), len(old), 'members', len(items))
    print('out', hashlib.sha256(new).hexdigest(), len(new), 'members', len(check))
    print('clients', names)
    print('ADDON_CLIENTS_PASS')


if __name__ == '__main__':
    main()
