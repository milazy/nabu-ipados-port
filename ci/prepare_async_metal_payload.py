"""Pack the qualified frontend addon and append trust without changing old modules."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
from audit_compositor_transport import EXPECTED,audit,cdhashes,need

def digest(data):return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('runtime','kernel','trustcache','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();base=a.runtime/'plugin'
    report=json.loads((base/'plugin-report.json').read_text())
    host=json.loads((base/'async-fix-host-report.json').read_text())
    need(host['status']=='ASYNC_METAL_FRONTEND_HOST_PASS' and host['async_cases']==20 and host['completion_wait_contract_preserved'] is True,'Host qualification missing')
    need(report['async_fix'] is True and report['completion_fix'] is False and report['fps_opt'] is False,'Wrong frontend variant')
    patches=list(report['adrenometal_patches'])
    need(len(patches)==5 and patches[-1]=='patches/adrenometal-nabu-async-creation.patch' and 'patches/adrenometal-nabu-completion-wait.patch' not in patches and 'patches/adrenometal-nabu-ci-kernels.patch' not in patches,'Unexpected patch combination')
    need(report['bundle_built'] and report['plugin_returncode']==0 and report['async_creation']['passed'],'Plugin build or async qualification failed')
    need(len(report['async_creation']['cases'])==20 and all(x['passed'] for x in report['async_creation']['cases']),'Async cases incomplete')
    fixed=digest((base/'async-source/NativeBridgeMetalFrontend.mm').read_bytes())
    need(report['async_creation']['fixed_source_sha256']==fixed,'Qualification source binding mismatch')
    need(report['abi_header_sha256']=='1608250c2c6cee12588a756f105bebc8652b03eb1ad383cc38eab8fa5da22734' and report['scanout_wire_sha256']=='3c91848ec16b02090d12862ca6e8cb61375488fa2885d141210cbc504d73984b','A640 ABI or scanout wire mismatch')
    need(report['adrenometal_commit']=='baad47ca22b181bf0ef0d08412d3ed1f96945e16' and report['metal2vulkan_commit']=='624bab3918de5b978e1101517abca2b4fa426565','Source pin mismatch')
    need(digest(a.kernel.read_bytes())=='e522b69aeaf901bc0188a79ed4860c3608a980021833a33a95ff65ab4a3c3b97','Installed kernel input changed')
    old=a.trustcache.read_bytes()
    need(digest(old)=='0a5679e8a6d49228a4c9bda6b6b0363b50e96f74047847dbb943c3aa426739b5','Expected previous trust cache')
    file_meta={x['path']:x['sha256'] for x in report['bundle_files']}
    file_meta.update({'deployment-inputs/'+name:value for name,value in report['undeployed'].items()})
    files={};newhashes=set();body=bytearray()
    for name,mode in EXPECTED.items():
        relative=name.removeprefix('addons/') if name.startswith('addons/') else 'deployment-inputs/'+name.split('/')[-1]
        data=(base/relative).read_bytes()
        need(digest(data)==file_meta[relative],'Build report mismatch: '+name)
        if mode==0o755:
            need(struct.unpack_from('<III',data)==(0xfeedfacf,0x100000c,0),'Expected ordinary ARM64 executable')
            for cd in cdhashes(data):
                need(cd['hash_type']==2,'Expected SHA-256 CodeDirectory')
                newhashes.add(bytes.fromhex(cd['cdhash']))
        files[name]=data;raw=name.encode()+b'\0';packed=zlib.compress(data,9)
        body+=struct.pack('<IIQQ',len(raw),mode,len(data),len(packed))
        body+=raw+b'\0'*((-len(raw))%8)+packed+b'\0'*((-len(packed))%8)
    addon=struct.pack('<8sIIQ',b'NGPUADD2',len(files),0,24+len(body))+body
    count=struct.unpack_from('<I',old)[0]
    offsets=list(struct.unpack_from('<'+'I'*count,old,4))+[len(old)]
    need(offsets[0]==4+4*count and offsets==sorted(set(offsets)),'Previous packed trust cache bounds')
    modules=[old[start:end] for start,end in zip(offsets,offsets[1:])]
    trusted=set()
    for m in modules:
        version=struct.unpack_from('<I',m)[0];n=struct.unpack_from('<I',m,20)[0];stride={0:20,1:22,2:24}[version]
        need(len(m)==24+n*stride,'Previous trust module length')
        trusted.update(m[24+i*stride:44+i*stride] for i in range(n))
    missing=sorted(newhashes-trusted);need(missing,'New plugin has no new CDHash')
    entries=b''.join(cd+bytes((2,0,0,0)) for cd in missing)
    uuid=hashlib.sha256(b'nabu-metal-async-v1'+entries).digest()[:16]
    modules.append(struct.pack('<I16sI',2,uuid,len(missing))+entries)
    starts=[];cursor=4+4*len(modules)
    for m in modules:starts.append(cursor);cursor+=len(m)
    cache=struct.pack('<I',len(modules))+struct.pack('<'+'I'*len(modules),*starts)+b''.join(modules)
    a.out.mkdir(parents=True,exist_ok=True)
    addonpath=a.out/'kernel-metal-async.macho.gpuaddon';tcpath=a.out/'kernel-metal-async.macho.trustcache';receipt=a.out/'payload-preparation.json'
    need(not any(x.exists() for x in (addonpath,tcpath,receipt)),'Prepared output already exists')
    addonpath.write_bytes(addon);tcpath.write_bytes(cache)
    checked=audit(a.kernel,addonpath,tcpath)
    result={'status':'ASYNC_METAL_PAYLOAD_HOST_PASS','kernel_path':str(a.kernel.resolve()),'kernel_sha256':digest(a.kernel.read_bytes()),'addon_path':str(addonpath.resolve()),'addon_sha256':digest(addon),'trustcache_path':str(tcpath.resolve()),'trustcache_sha256':digest(cache),'old_trustcache_sha256':digest(old),'preserved_module_sha256':[digest(m) for m in modules[:-1]],'new_cdhashes':[x.hex() for x in missing],'async_cases':20,'transport':checked,'boot_verified':False}
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],result['addon_sha256'],result['trustcache_sha256'])
if __name__=='__main__':main()
