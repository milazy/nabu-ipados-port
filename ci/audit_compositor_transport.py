#!/usr/bin/env python3
"""Check the standard GPU addon, its signed binaries, and the matching kernel gate."""
import argparse,hashlib,json,plistlib,struct,zlib
from pathlib import Path
EXPECTED={
 'addons/NativeAdrenoMetal.bundle/Info.plist':0o644,
 'addons/NativeAdrenoMetal.bundle/NativeAdrenoMetal':0o755,
 'addons/NativeAdrenoMetal.bundle/_CodeSignature/CodeResources':0o644,
 'addons/NativeAdrenoMetal.bundle/libvulkan_freedreno.dylib':0o755,
 'bin/adrenoprobed':0o755,
 'daemons/com.apple.bluetoothd.plist':0o644,
 'daemons/com.apple.iomfb_fdr_loader.plist':0o644,
 'daemons/org.blu-sharky.adrenoprobed.plist':0o644,
}
def need(ok,why):
    if not ok: raise ValueError(why)
def cdhashes(b):
    need(b[:4]==bytes.fromhex('cffaedfe'),'Expected thin ARM64 Mach-O')
    count,extent=struct.unpack_from('<II',b,16);at=32;sig=None
    for _ in range(count):
        cmd,size=struct.unpack_from('<II',b,at)
        need(size>=8 and at+size<=32+extent,'Invalid load command')
        if cmd==0x1d:
            offset,length=struct.unpack_from('<II',b,at+8)
            need(offset+length<=len(b),'Signature bounds')
            sig=b[offset:offset+length]
        at+=size
    need(sig is not None,'Unsigned addon executable')
    magic,total,count=struct.unpack_from('>III',sig)
    need(magic==0xfade0cc0 and total<=len(sig),'Signature superblob invalid')
    result=[]
    for i in range(count):
        slot,off=struct.unpack_from('>II',sig,12+i*8)
        magic,length=struct.unpack_from('>II',sig,off)
        need(off+length<=total,'Signature child bounds')
        if magic!=0xfade0c02: continue
        cd=sig[off:off+length];hash_type=cd[37]
        need(hash_type in (1,2,3,4),'Unknown CodeDirectory hash')
        digest=(hashlib.sha1(cd).digest() if hash_type==1 else
                hashlib.sha384(cd).digest() if hash_type==4 else hashlib.sha256(cd).digest())[:20]
        result.append({'hash_type':hash_type,'cdhash':digest.hex()})
    need(result,'No CodeDirectory')
    return result

def audit(kernel,addon,trustcache):
    k=kernel.read_bytes();b=addon.read_bytes();tc=trustcache.read_bytes()
    for marker in (b'sheng-gpu-addon',b'NativeAdrenoMetal.bundle/Info.plist',b'GpuAddon'):
        need(marker in k,'Kernel standard addon support missing: '+marker.decode())
    need(b[:8]==b'NGPUADD2','Addon envelope magic')
    count,reserved,total=struct.unpack_from('<IIQ',b,8)
    need(count==len(EXPECTED) and reserved==0 and total==len(b),'Expected standard eight-file addon')
    modules=struct.unpack_from('<I',tc)[0]
    need(1<=modules<=16 and len(tc)>=4+4*modules,'Invalid packed trust cache header')
    offsets=list(struct.unpack_from('<'+'I'*modules,tc,4))+[len(tc)]
    need(offsets[0]==4+4*modules and offsets==sorted(set(offsets)),'Invalid trust cache module offsets')
    trusted=set()
    for start,end in zip(offsets,offsets[1:]):
        module=tc[start:end]
        need(len(module)>=24,'Truncated trust cache module')
        version=struct.unpack_from('<I',module)[0];n=struct.unpack_from('<I',module,20)[0]
        stride={0:20,1:22,2:24}.get(version)
        need(stride is not None and 24+n*stride==len(module),'Trust cache module shape unsupported')
        trusted.update(module[24+i*stride:44+i*stride] for i in range(n))
    at=24;files={};report=[]
    for _ in range(count):
        names,mode,size,packed=struct.unpack_from('<IIQQ',b,at);at+=24
        need(2<=names<=160 and size<=67108864 and packed<=len(b)-at,'Addon entry bounds')
        raw=b[at:at+names];need(raw.endswith(b'\0') and b'\0' not in raw[:-1],'Invalid name')
        name=raw[:-1].decode();at+=(names+7)&~7
        need(name in EXPECTED and mode==EXPECTED[name] and name not in files,'Unexpected addon file or mode')
        content=zlib.decompress(b[at:at+packed]);need(len(content)==size,'Addon expansion mismatch')
        files[name]=content;at+=(packed+7)&~7
        item={'name':name,'bytes':size,'sha256':hashlib.sha256(content).hexdigest()}
        if mode==0o755:
            item['code_directories']=cdhashes(content)
            need(any(bytes.fromhex(x['cdhash']) in trusted for x in item['code_directories']),
                 'Executable not in paired trust cache: '+name)
            item['cdhash_in_paired_trustcache']=True
        report.append(item)
    need(at==len(b) and set(files)==set(EXPECTED),'Addon trailing data or missing member')
    info=plistlib.loads(files['addons/NativeAdrenoMetal.bundle/Info.plist'])
    need(info['CFBundleExecutable']=='NativeAdrenoMetal','Unexpected Metal bundle executable')
    need(info['NSPrincipalClass']=='NativeAdrenoMetalDevice','Unexpected Metal principal class')
    for name,content in files.items():
        if name.startswith('daemons/'):
            job=plistlib.loads(content)
            need(job.get('ProgramArguments')==['/private/var/ngpu/bin/adrenoprobed'],'Unexpected addon job program')
    return {'status':'STANDARD_COMPOSITOR_TRANSPORT_HOST_PASS','required_boot_argument':'sheng-gpu-addon=1',
      'kernel_sha256':hashlib.sha256(k).hexdigest(),'addon_sha256':hashlib.sha256(b).hexdigest(),
      'trustcache_sha256':hashlib.sha256(tc).hexdigest(),'files':report,'boot_proven':False}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ('kernel','addon','trustcache','report'):p.add_argument('--'+x,type=Path,required=True)
    a=p.parse_args();need(not a.report.exists(),'Report already exists')
    r=audit(a.kernel,a.addon,a.trustcache);a.report.write_text(json.dumps(r,indent=2)+'\n')
    print(r['status']);print('All three executable CDHashes match the paired trust cache.')
if __name__=='__main__':main()
