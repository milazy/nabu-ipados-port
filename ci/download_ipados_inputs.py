# Fetch only the five build-required entries from the official Apple IPSW.
# Uses HTTPS range requests (not a full 6.86 GB download) and validates SHA256.
# Output stays on this PC; Apple-copyrighted materials are NOT redistributed.
import hashlib, io, json, pathlib, plistlib, sys, urllib.request, zipfile, importlib.util
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT/'nabu-source'
spec = importlib.util.spec_from_file_location('prepare_ipsw_input', REPO/'source-ci'/'prepare_ipsw_input.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)
URL = 'https://updates.cdn-apple.com/2024FallFCS/fullrestores/062-78914/A081E8C4-D00A-4FC5-A650-A42EA1726236/iPad_10.2_17.7_21H16_Restore.ipsw'

class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=50) as r:
            self.length = int(r.headers['Content-Length'])
        self.start, self.cache = -1, b''
        self.transferred = 0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        dest = offset if whence == 0 else self.pos + offset if whence == 1 else self.length + offset
        if not 0 <= dest <= self.length: raise OSError('seek outside IPSW')
        self.pos = dest
        return self.pos
    def read(self, n=-1):
        if n == -1: n = self.length - self.pos
        if n == 0 or self.pos == self.length: return b''
        n = min(n, self.length-self.pos)
        if self.start <= self.pos and self.pos+n <= self.start+len(self.cache):
            out = self.cache[self.pos-self.start:self.pos-self.start+n]
            self.pos += len(out)
            return out
        amount = min(self.length-self.pos, max(n, 1024*1024))
        end = self.pos + amount - 1
        req = urllib.request.Request(self.url, headers={'Range':f'bytes={self.pos}-{end}'})
        with urllib.request.urlopen(req, timeout=120) as r:
            if r.status != 206 or not r.headers.get('Content-Range','').startswith(f'bytes {self.pos}-{end}/'):
                raise RuntimeError('Server returned unexpected Range response')
            data = r.read()
        if len(data) != amount: raise RuntimeError('Short range read')
        self.start, self.cache = self.pos, data
        self.transferred += len(data)
        self.pos += n
        return data[:n]

def main():
    target = ROOT/'ipsw-21h16-small.zip'
    if target.exists(): raise RuntimeError('Output already exists: refusing overwrite')
    reader = HTTPRangeReader(URL)
    print(f'Official Apple IPSW size: {reader.length:,} bytes', flush=True)
    source = zipfile.ZipFile(reader)
    manifest_bytes = source.read('BuildManifest.plist')
    manifest = plistlib.loads(manifest_bytes)
    board = project.identity(manifest)
    entries = {'BuildManifest.plist':manifest_bytes}
    digests = {}
    for component in project.COMPONENTS:
        name = board['Manifest'][component]['Info']['Path']
        print(f'Fetching {component}: {name}', flush=True)
        data = source.read(name)
        digest = hashlib.sha256(data).hexdigest()
        pin = project.MEMBER_SHA256.get(pathlib.PurePosixPath(name).name)
        if pin and digest != pin: raise RuntimeError(f'SHA256 failed: {name} got {digest}')
        entries[name], digests[name] = data, digest
        print(f'  OK: {len(data):,} bytes, SHA256 {digest}',flush=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(entries):
            zi = zipfile.ZipInfo(name, project.ZIP_EPOCH)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0o600 << 16
            output.writestr(zi, entries[name])
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {'source':URL, 'time':datetime.now(timezone.utc).isoformat(),
              'ipsw_size':reader.length, 'downloaded_bytes':reader.transferred,
              'inputs':digests, 'archive':str(target), 'archive_sha256':sha,
              'matches_maintainer_input':sha==project.EXPECTED_ARCHIVE_SHA256}
    target.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PACKAGE_READY='+str(target), flush=True)
    print('MATCHES_MAINTAINER_INPUT='+str(report['matches_maintainer_input']),flush=True)
if __name__ == '__main__':
    main()
