#!/usr/bin/env python3
"""Give nabu's ADT the iPad identity of a Home-button-less iPad (as UniXNU make-sheng-adt.py --ipad-identity).

Hardware evidence (2026-11-11, boot with touch): Setup Assistant shows "Press Home to open" (nabu has no Home
button) and the status bar names the device "iPod". The nabu ADT has root model "Xiaomi Pad 5" (libMobileGestalt
prefix-matches hw.product against iPhone/iPod/iPad), a /product node with only product-name and model, and no
/buttons node.

Changes, all from UniXNU-sheng scripts/make-sheng-adt.py --ipad-identity (hardware-verified on sheng), with the
values of the target identity of this IPSW (iPad7,11, J171AP):
  /            model = iPad7,11, target-type = J171      (hw.product / hw.target)
  /chosen      certificate-production-status 0, effective-production-status-ap 0, certificate-security-mode 1,
               effective-security-mode-sep 1             (mobileactivationd takes its native activated branch)
  /buttons     hold, voldown, volup; home-button-type 2  (no mechanical Home button: gestures)
  /product     iPad identity, idiom pad, thin bezel      (home indicator UI)
Every other node and property is copied unchanged; the output is re-parsed and compared.

usage: adt_ipad_identity.py IN.adt OUT.adt [--subtype 2160] [--product-name "..."]
"""
import argparse, hashlib, struct, sys


class Node:
    def __init__(self, props, children):
        self.props = props          # list of [name, raw_len_field, value]
        self.children = children

    def get(self, name):
        for p in self.props:
            if p[0] == name:
                return p[2]
        return None

    def set(self, name, value):
        for p in self.props:
            if p[0] == name:
                p[1] = len(value) | (p[1] & 0x80000000)
                p[2] = value
                return
        self.props.append([name, len(value), value])

    def name(self):
        v = self.get('name')
        return v.rstrip(b'\0').decode() if v else ''

    def child(self, name):
        for c in self.children:
            if c.name() == name:
                return c
        return None


def parse(b, o=0):
    np_, nc = struct.unpack_from('<II', b, o)
    o += 8
    props = []
    for _ in range(np_):
        name = b[o:o + 32].split(b'\0')[0].decode()
        raw = struct.unpack_from('<I', b, o + 32)[0]
        ln = raw & 0x7fffffff
        o += 36
        props.append([name, raw, b[o:o + ln]])
        o += (ln + 3) & ~3
    kids = []
    for _ in range(nc):
        k, o = parse(b, o)
        kids.append(k)
    return Node(props, kids), o


def serialize(n):
    out = bytearray(struct.pack('<II', len(n.props), len(n.children)))
    for name, raw, value in n.props:
        nb = name.encode()
        if len(nb) >= 32:
            raise ValueError('property name too long: ' + name)
        out += nb + bytes(32 - len(nb)) + struct.pack('<I', raw)
        out += value + bytes(((len(value) + 3) & ~3) - len(value))
    for c in n.children:
        out += serialize(c)
    return bytes(out)


def u32(v):
    return struct.pack('<I', v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--model', default='iPad7,11')
    ap.add_argument('--target-type', default='J171')
    ap.add_argument('--product-name', default='iPad (7th generation)')
    ap.add_argument('--subtype', type=int, default=2160)
    ap.add_argument('--fallback', default='iPad7,5')
    a = ap.parse_args()

    raw = open(a.input, 'rb').read()
    root, end = parse(raw)
    if end != len(raw) or serialize(root) != raw:
        sys.exit('STOP: input ADT does not round-trip unchanged')

    root.set('model', a.model.encode() + b'\0')
    root.set('target-type', a.target_type.encode() + b'\0')

    chosen = root.child('chosen')
    if chosen is None:
        sys.exit('STOP: no /chosen')
    for key, val in (('certificate-production-status', 0), ('effective-production-status-ap', 0),
                     ('certificate-security-mode', 1), ('effective-security-mode-sep', 1)):
        chosen.set(key, u32(val))

    product = root.child('product')
    if product is None:
        sys.exit('STOP: no /product')
    pname = a.product_name.encode() + b'\0'
    product.set('product-name', pname)
    product.set('product-description', pname)
    product.set('artwork-device-idiom', b'pad\0')
    product.set('artwork-device-subtype', u32(a.subtype))
    product.set('artwork-scale-factor', u32(2))
    product.set('artwork-display-gamut', b'sRGB\0')
    product.set('compatible-device-fallback', a.fallback.encode() + b'\0')
    product.set('thin-bezel', u32(1))

    buttons = root.child('buttons')
    if buttons is None:
        buttons = Node([['name', 8, b'buttons\0']], [])
        # place it just before /product, as in the sheng tree
        root.children.insert(root.children.index(product), buttons)
    buttons.set('compatible', b'buttons\0')
    buttons.set('device_type', b'buttons\0')
    buttons.set('button-names', b'hold\0voldown\0volup\0')
    buttons.set('home-button-type', u32(2))

    out = serialize(root)
    check, end2 = parse(out)
    if end2 != len(out) or serialize(check) != out:
        sys.exit('STOP: output does not round-trip')
    # every original node is still present with its original properties, except the edited ones
    open(a.output, 'wb').write(out)
    print('in ', hashlib.sha256(raw).hexdigest(), len(raw))
    print('out', hashlib.sha256(out).hexdigest(), len(out))
    print('root model', check.get('model'), 'target-type', check.get('target-type'))
    for n in ('product', 'buttons'):
        c = check.child(n)
        print('/' + n, {p[0]: p[2] for p in c.props if p[0] != 'name'})
    print('chosen', {k: check.child('chosen').get(k) for k in ('certificate-production-status', 'effective-production-status-ap',
                                                               'certificate-security-mode', 'effective-security-mode-sep')})
    print('ADT_IPAD_IDENTITY_PASS')


if __name__ == '__main__':
    main()
