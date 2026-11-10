"""Download one successful, source-bound runtime artifact and verify its ZIP digest."""
import argparse,hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
REPO='beamerwz/nabu-ipados-macos-build'
def api(path):
    r=subprocess.run(['gh','api','repos/'+REPO+'/'+path],capture_output=True,timeout=300)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-500:])
    return r.stdout
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact-id',type=int,required=True);p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--source',required=True);p.add_argument('--sha256',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert re.fullmatch('[0-9a-f]{64}',a.sha256) and re.fullmatch('[0-9a-f]{40}',a.source)
    assert not a.out.exists(),'Extraction directory already exists'
    run=json.loads(api(f'actions/runs/{a.run_id}'))
    assert run['conclusion']=='success' and run['head_sha']==a.source,'Run not successful or source differs'
    meta=json.loads(api(f'actions/artifacts/{a.artifact_id}'))
    assert meta['name']=='nabu-metal-async-fix' and not meta['expired']
    assert meta['workflow_run']['id']==a.run_id and meta['workflow_run']['head_sha']==a.source
    assert meta['digest']=='sha256:'+a.sha256,'Advertised artifact digest changed'
    archive=a.out.with_suffix('.zip');archive.parent.mkdir(parents=True,exist_ok=True)
    data=archive.read_bytes() if archive.exists() else api(f'actions/artifacts/{a.artifact_id}/zip')
    assert hashlib.sha256(data).hexdigest()==a.sha256,'Artifact ZIP checksum mismatch'
    if not archive.exists():archive.write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sum(x.file_size for x in z.infolist())<=512*1024*1024,'Oversized artifact'
        for x in z.infolist():
            path=Path(x.filename)
            assert not path.is_absolute() and '..' not in path.parts and ':' not in x.filename,'Unsafe archive path'
        assert z.testzip() is None,'Corrupt archive entry'
        z.extractall(a.out)
    host=json.loads((a.out/'runtime/plugin/async-fix-host-report.json').read_text())
    assert host['status']=='ASYNC_METAL_FRONTEND_HOST_PASS' and host['async_cases']==20
    print('SOURCE_BOUND_ARTIFACT_ZIP_PASS',a.sha256,a.out)
if __name__=='__main__':main()
