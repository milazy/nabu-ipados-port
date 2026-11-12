#!/usr/bin/env python3
"""Merge owner jobs and selected environment overrides into the original 21H16 launchd cache (macOS only).

Every original entry is preserved unchanged except the EnvironmentVariables of the selected OS jobs. The result is
converted with Apple's plutil (binary1) and signed with a detached ad-hoc signature; its CDHash must be added to the
owner trust module (tools/addon_add_payload.py --cdhash). Follows UniXNU scripts/build-boot-runtime.py
merge_launchd_cache/sign_launchd_cache.

usage: build_launchd_cache.py --source launchd.plist --job JOB.plist [--job ...] [--env LABEL:KEY=VALUE ...] --out DIR
"""
import argparse, copy, hashlib, json, plistlib, re, subprocess
from pathlib import Path


def run(*a, **k):
    return subprocess.run([str(x) for x in a], check=True, **k)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--job', type=Path, action='append', default=[])
    p.add_argument('--env', action='append', default=[])
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    raw = a.source.read_bytes()
    original = plistlib.loads(raw)
    merged = copy.deepcopy(original)
    jobs = merged['LaunchDaemons']
    added = []
    for path in a.job:
        job = plistlib.loads(path.read_bytes())
        assert job['Label'].startswith('org.nabu.'), path
        key = '/System/Library/LaunchDaemons/' + job['Label'] + '.plist'
        assert key not in jobs, key
        assert job['ProgramArguments'][0].startswith('/usr/bin/'), 'xpcproxy execs only outside /private/var'
        jobs[key] = job
        added.append(key)
    envs = {}
    for spec in a.env:
        label, _, kv = spec.partition(':')
        k, _, v = kv.partition('=')
        envs.setdefault(label, {})[k] = v
    changed = []
    for label, env in envs.items():
        keys = [k for k, j in original['LaunchDaemons'].items() if j.get('Label') == label]
        assert len(keys) == 1, f'{label}: {len(keys)} jobs'
        jobs[keys[0]].setdefault('EnvironmentVariables', {}).update(env)
        changed.append(keys[0])
    for k, v in original.items():
        if k != 'LaunchDaemons':
            assert merged[k] == v
    for k, v in original['LaunchDaemons'].items():
        if k not in changed:
            assert jobs[k] == v
    a.out.mkdir(parents=True, exist_ok=True)
    dest = a.out / 'launchd.plist'
    dest.write_bytes(plistlib.dumps(merged, fmt=plistlib.FMT_XML, sort_keys=False))
    run('plutil', '-convert', 'binary1', dest)
    assert plistlib.loads(dest.read_bytes()) == merged
    sig = a.out / 'launchd.plist.sig'
    run('codesign', '--force', '--sign', '-', '--pagesize', '4096', '--digest-algorithm', 'sha256',
        '--identifier', 'org.nabu.launchd-cache', '--detached', sig, dest)
    run('codesign', '--verify', '--strict', '--detached', sig, dest)
    detail = run('codesign', '--display', '--verbose=4', '--detached', sig, dest, capture_output=True, text=True).stderr
    cdhash = re.search(r'^CDHash=([0-9a-f]{40})$', detail, re.M)[1]
    report = dict(source_sha256=hashlib.sha256(raw).hexdigest(), source_version=original.get('VersionNumber'),
                  original_jobs=len(original['LaunchDaemons']), added_jobs=added, env_changed=changed, env=envs,
                  output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                  signature_sha256=hashlib.sha256(sig.read_bytes()).hexdigest(), cdhash=cdhash)
    (a.out / 'launchd-cache.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
