#!/usr/bin/env python3
"""Stream only the root OS image of the official iPadOS 17.7 (21H16) IPSW to disk with HTTPS range requests.

usage: fetch_os_image.py OUT.dmg   (writes OUT.dmg and OUT.dmg.json; nothing Apple-owned is redistributed)
"""
import hashlib, io, json, plistlib, sys, urllib.request, zipfile
from pathlib import Path

URL = ('https://updates.cdn-apple.com/2024FallFCS/fullrestores/062-78914/A081E8C4-D00A-4FC5-A650-A42EA1726236/'
       'iPad_10.2_17.7_21H16_Restore.ipsw')
CHUNK = 64 << 20


class Range(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.start, self.cache = url, 0, -1, b''
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60) as r:
            self.length = int(r.headers['Content-Length'])
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.length + off
        return self.pos
    def read(self, n=-1):
        if n < 0: n = self.length - self.pos
        n = min(n, self.length - self.pos)
        if n <= 0: return b''
        if not (self.start <= self.pos and self.pos + n <= self.start + len(self.cache)):
            amount = min(self.length - self.pos, max(n, CHUNK if n > 1 << 16 else 1 << 20))
            end = self.pos + amount - 1
            for attempt in range(5):
                try:
                    req = urllib.request.Request(self.url, headers={'Range': f'bytes={self.pos}-{end}'})
                    with urllib.request.urlopen(req, timeout=300) as r:
                        assert r.status == 206
                        data = r.read()
                    if len(data) == amount: break
                except Exception as e:
                    print('retry', attempt, e, flush=True)
            else:
                raise SystemExit('range read failed')
            self.start, self.cache = self.pos, data
        out = self.cache[self.pos - self.start:self.pos - self.start + n]
        self.pos += len(out)
        return out


def main():
    out = Path(sys.argv[1])
    z = zipfile.ZipFile(Range(URL))
    manifest = plistlib.loads(z.read('BuildManifest.plist'))
    assert manifest['ProductBuildVersion'] == '21H16', manifest['ProductBuildVersion']
    paths = {i['Manifest']['OS']['Info']['Path'] for i in manifest['BuildIdentities'] if 'OS' in i['Manifest']}
    assert len(paths) == 1, paths
    name = paths.pop()
    info = z.getinfo(name)
    print('OS image', name, info.file_size, flush=True)
    digest = hashlib.sha256()
    with z.open(name) as src, out.open('wb') as dst:
        done = 0
        while True:
            block = src.read(CHUNK)
            if not block: break
            dst.write(block); digest.update(block); done += len(block)
            print(f'  {done >> 20} / {info.file_size >> 20} MiB', flush=True)
    assert done == info.file_size
    report = {'ipsw': URL, 'member': name, 'bytes': done, 'sha256': digest.hexdigest()}
    Path(str(out) + '.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
