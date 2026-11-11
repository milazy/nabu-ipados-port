#!/usr/bin/env python3
"""Add the /nabu-touch node that platform/NabuTouch.cpp reads to a nabu ADT.

NabuTouch (zzweiqing/UniXNU-nabu) downloads the NT36523 firmware itself and reads it, with its
partition list and hardware-CRC bank, from the private ADT node /nabu-touch. The node builder is not
part of the public repository; this tool rebuilds it from the vendor firmware file.

Firmware choice: the official nabu device tree (MiCode Xiaomi_Kernel_OpenSource, nabu-r-oss,
arch/arm64/boot/dts/qcom/nabu-sm8150.dtsi) lists novatek_nt36523_fw01.bin first; nvt_get_panel_type()
picks index 0 for lockdown byte 0x42 ("This is CSOT Display Panel!") and index 1 for 0x36 (Tianma).

Parser: a line-by-line port of nvt_bin_header_parser() from the same tree
(drivers/input/touchscreen/nt36523/nt36xxx_fw_update.c). NT36523_hw_info.hw_crc = 2, so every CRC is
read from the header. nvt_write_firmware() skips zero-size partitions and writes size + 1 bytes.

Properties written (little-endian u32 arrays):
  name        "nabu-touch"
  firmware    the vendor file, unchanged
  partitions  {sram, bin, bytes-to-write} per non-empty partition
  crc-bank    {ILM sram, ILM size, ILM crc, DLM sram, DLM size, DLM crc}
"""
import argparse
import hashlib
import struct
import sys
from pathlib import Path

ILM_DLM = 2


def word(d, pos):
    if pos < 0 or pos + 4 > len(d):
        raise ValueError('header word at %#x outside the file' % pos)
    return struct.unpack_from('<I', d, pos)[0]


def parse_firmware(d):
    end = word(d, 0)
    cascade = (d[0x20] & 0x02) >> 1
    info = 0
    pos = 0x30
    if cascade:
        while pos < end // 2:
            info += 1
            pos += 0x10
        info += 1
    else:
        while pos < end:
            info += 1
            pos += 0x10
    ovly_info = (d[0x28] & 0x10) >> 4
    ovly = (d[0x28] & 0x0f) if ovly_info else 0
    count = ILM_DLM + ovly + info
    parts = []
    found_header = False
    for i in range(count):
        if i < ILM_DLM:
            p = {'bin': word(d, i * 12), 'sram': word(d, 4 + i * 12), 'size': word(d, 8 + i * 12),
                 'crc': word(d, 0x18 + i * 4), 'name': 'ILM' if i == 0 else 'DLM'}
        elif i < ILM_DLM + info:
            if not found_header:
                pos = 0x30 + 0x10 * (i - ILM_DLM)
            elif cascade:
                pos = end - 0x10
            p = {'sram': word(d, pos), 'size': word(d, pos + 4), 'bin': word(d, pos + 8), 'crc': word(d, pos + 12)}
            if p['bin'] < end and p['size'] != 0:
                p['name'] = 'Header'
                found_header = True
            else:
                p['name'] = 'Info-%d' % (i - ILM_DLM)
        else:
            pos = parts[1]['bin'] + 0x10 * (i - ILM_DLM - info)
            p = {'sram': word(d, pos), 'size': word(d, pos + 4), 'bin': word(d, pos + 8), 'crc': word(d, pos + 12),
                 'name': 'Overlay-%d' % (i - ILM_DLM - info)}
        if p['bin'] + p['size'] > len(d):
            raise ValueError('%s range %#x+%#x past the file' % (p['name'], p['bin'], p['size']))
        parts.append(p)
    return parts, {'end': end, 'cascade': cascade, 'info': info, 'overlay': ovly}


def write_list(parts, size):
    out = []
    for p in parts:
        if not p['size']:
            continue
        n = p['size'] + 1
        if p['bin'] + n > size:
            n = p['size']
        out.append((p['sram'], p['bin'], n))
    return out


# ---------------------------------------------------------------- ADT
def adt_node_end(d, at):
    if at + 8 > len(d):
        raise ValueError('node header past the end at %#x' % at)
    nprops, nchildren = struct.unpack_from('<II', d, at)
    pos = at + 8
    names = []
    for _ in range(nprops):
        name = d[pos:pos + 32].split(b'\0', 1)[0]
        length = struct.unpack_from('<I', d, pos + 32)[0] & 0x7fffffff
        pos += 36 + ((length + 3) & ~3)
        if pos > len(d):
            raise ValueError('property past the end')
        names.append(name)
    for _ in range(nchildren):
        pos, _ = adt_node_end(d, pos)
    return pos, names


def child_names(d):
    nprops, nchildren = struct.unpack_from('<II', d, 0)
    pos = 8
    for _ in range(nprops):
        length = struct.unpack_from('<I', d, pos + 32)[0] & 0x7fffffff
        pos += 36 + ((length + 3) & ~3)
    names = []
    for _ in range(nchildren):
        nxt, props = adt_node_end(d, pos)
        sub = d[pos:nxt]
        # find the "name" property value of this child
        q = 8
        for _ in range(struct.unpack_from('<I', sub, 0)[0]):
            pname = sub[q:q + 32].split(b'\0', 1)[0]
            length = struct.unpack_from('<I', sub, q + 32)[0] & 0x7fffffff
            if pname == b'name':
                names.append(sub[q + 36:q + 36 + length].split(b'\0', 1)[0].decode())
            q += 36 + ((length + 3) & ~3)
        pos = nxt
    return names


def prop(name, value):
    if len(name) >= 32:
        raise ValueError('property name too long')
    pad = (-len(value)) % 4
    return name.encode().ljust(32, b'\0') + struct.pack('<I', len(value)) + value + b'\0' * pad


def build_node(fw, parts_list, bank):
    props = [
        prop('name', b'nabu-touch\0'),
        prop('firmware', fw),
        prop('partitions', b''.join(struct.pack('<3I', *t) for t in parts_list)),
        prop('crc-bank', struct.pack('<6I', *bank)),
    ]
    return struct.pack('<II', len(props), 0) + b''.join(props)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--adt', type=Path, required=True)
    ap.add_argument('--firmware', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    adt = a.adt.read_bytes()
    fw = a.firmware.read_bytes()
    end, _ = adt_node_end(adt, 0)
    if end != len(adt):
        raise SystemExit('ADT does not parse to its own length (%#x of %#x)' % (end, len(adt)))
    names = child_names(adt)
    if 'nabu-touch' in names:
        raise SystemExit('ADT already has /nabu-touch')
    parts, meta = parse_firmware(fw)
    plist = write_list(parts, len(fw))
    bank = (parts[0]['sram'], parts[0]['size'], parts[0]['crc'], parts[1]['sram'], parts[1]['size'], parts[1]['crc'])
    for p in parts:
        print('  %-9s sram=%#08x size=%#07x bin=%#07x crc=%#010x' % (p['name'], p['sram'], p['size'], p['bin'], p['crc']))
    print('header', meta, 'write list', [tuple(hex(x) for x in t) for t in plist])
    print('crc-bank', [hex(x) for x in bank])
    node = build_node(fw, plist, bank)
    nprops, nchildren = struct.unpack_from('<II', adt, 0)
    out = struct.pack('<II', nprops, nchildren + 1) + adt[8:] + node
    end, _ = adt_node_end(out, 0)
    if end != len(out) or 'nabu-touch' not in child_names(out) or out[:len(adt)][8:] != adt[8:]:
        raise SystemExit('rebuilt ADT failed verification')
    a.out.write_bytes(out)
    print('root children %d -> %d, bytes %d -> %d' % (nchildren, nchildren + 1, len(adt), len(out)))
    print('firmware sha256', hashlib.sha256(fw).hexdigest())
    print('out sha256', hashlib.sha256(out).hexdigest())


if __name__ == '__main__':
    main()
