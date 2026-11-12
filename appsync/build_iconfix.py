#!/usr/bin/env python3
"""Build the nabu icon fix: NabuIconFix.dylib and a signed iconservicesagent copy that loads it (macOS, Xcode).

usage: build_iconfix.py --os-root MOUNTED_21H16_OS --output DIR
Outputs DIR/NabuIconFix.dylib and DIR/iconservicesagent (to addon bin/, shown at /usr/bin through the owner union),
and DIR/report.json. The launchd cache points the iconservicesagent job at /usr/bin/iconservicesagent
(ci/build_launchd_cache.py --program). Same technique as appsync/build.py: the copy's Foundation dependency is renamed
to the library, which re-exports Foundation.
"""
import argparse, hashlib, json, plistlib, re, subprocess
from pathlib import Path
from macho import add_dylib

ROOT = Path(__file__).resolve().parent
SOURCE = 'System/Library/CoreServices/iconservicesagent'
DYLIB = '/usr/bin/NabuIconFix.dylib'


def run(*a, capture=False):
    return subprocess.run([str(x) for x in a], check=True, capture_output=capture, text=capture)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--os-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    sdk = run('xcrun', '--sdk', 'iphoneos', '--show-sdk-path', capture=True).stdout.strip()
    lib = out / 'NabuIconFix.dylib'
    run('xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-fobjc-arc', '-O2', '-Wall', '-Werror',
        '-framework', 'Foundation', '-dynamiclib', ROOT / 'IconFix.m', '-install_name', DYLIB,
        '-Wl,-reexport_framework,Foundation', '-Wl,-compatibility_version,3000', '-Wl,-current_version,5027.0.69', '-o', lib)
    run('codesign', '--force', '--sign', '-', '--pagesize', '4096', '--identifier', 'org.nabu.iconfix', lib)
    original = a.os_root / SOURCE
    data = original.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = out / 'iconservicesagent'
    target.write_bytes(add_dylib(data, DYLIB, digest))
    target.chmod(0o755)
    before = run('codesign', '-d', '--entitlements', ':-', original, capture=True).stdout
    run('codesign', '--force', '--sign', '-', '--pagesize', '4096', '--digest-algorithm', 'sha256',
        '--preserve-metadata=identifier,entitlements,flags', target)
    run('codesign', '--verify', '--strict', target)
    after = run('codesign', '-d', '--entitlements', ':-', target, capture=True).stdout
    if (plistlib.loads(before.encode()) if before.strip() else {}) != (plistlib.loads(after.encode()) if after.strip() else {}):
        raise SystemExit('entitlements changed')
    report = dict(source=SOURCE, source_sha256=digest, dylib=DYLIB,
                  outputs={f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (lib, target)})
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
