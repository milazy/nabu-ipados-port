"""Rebuild only the async frontend; reuse the exact previously built A640 Turnip."""
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
REPO='beamerwz/nabu-ipados-macos-build'
ARTIFACT=13613094307
ARCHIVE_SHA='4401ead60dbb6803ea0d5552cf98cd2857ad6fce9c1b9fd03fcc2fd05e0ccbce'
CORE='cd2dd1bd0d79a441424f2bd014144bd719ba56f7'
MESA='85fda3b36405bcaea8bffc64aa4f2651dc90770d'
def sha(data):return hashlib.sha256(data).hexdigest()
def run(*args):subprocess.run(list(map(str,args)),check=True)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('device','work','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();device=a.device.resolve();work=a.work.resolve();out=a.output.resolve()
    assert sys.platform=='darwin' and os.environ.get('GITHUB_ACTIONS')=='true'
    assert not work.exists() and not out.exists()
    result=subprocess.run(['gh','api',f'repos/{REPO}/actions/artifacts/{ARTIFACT}/zip'],capture_output=True,timeout=300)
    assert result.returncode==0,result.stderr.decode(errors='replace')[-400:]
    assert sha(result.stdout)==ARCHIVE_SHA,'Reference artifact digest mismatch'
    import io
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as z:
        library=z.read('runtime/libvulkan_freedreno.dylib')
        ref=json.loads(z.read('runtime/turnip-report.json'))
    assert ref['unixnu_commit']==CORE and ref['mesa_commit']==MESA
    assert ref['build_returncode']==0 and ref['library_built']
    assert sha(library)==ref['library_sha256'] and len(library)==ref['library_bytes']
    run('git','init','-q',work);run('git','-C',work,'remote','add','origin','https://github.com/UniXNU/UniXNU.git')
    run('git','-C',work,'fetch','-q','--depth','1','origin',CORE);run('git','-C',work,'checkout','-q','--detach','FETCH_HEAD')
    pins=json.loads((work/'scripts/data/adreno-compiler-inputs.json').read_text())
    assert pins['mesa']['commit']==MESA
    headers=work/'.cache/mesa-work';headers.parent.mkdir(exist_ok=True)
    run('git','init','-q',headers);run('git','-C',headers,'remote','add','origin',pins['mesa']['mirror'])
    run('git','-C',headers,'fetch','-q','--depth','1','--filter=blob:none','origin',MESA)
    run('git','-C',headers,'sparse-checkout','set','--cone','include')
    run('git','-C',headers,'checkout','-q','--detach','FETCH_HEAD')
    assert (headers/'include/vulkan/vulkan.h').is_file(),'Pinned Vulkan headers missing'
    target=work/'build/mesa-tu-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib';target.parent.mkdir(parents=True);target.write_bytes(library)
    out.mkdir(parents=True)
    reference={'artifact_run':42469765851,'artifact_id':ARTIFACT,'artifact_zip_sha256':ARCHIVE_SHA,'library_sha256':sha(library),'library_bytes':len(library),'abi_header_sha256':ref['abi_header_sha256'],'unixnu_commit':CORE,'mesa_commit':MESA,'hardware_tested':False}
    (out/'turnip-reference.json').write_text(json.dumps(reference,indent=2)+'\n')
    sys.path.insert(0,str(device/'source-ci'))
    import nabu_metal_plugin_ci as plugin
    # Apply the wait-completion correction after the async-creation patch has
    # been applied, before compiling the combined plugin. The two patches
    # touch different methods; git apply hunk offsets were stale but these
    # exact source statements are stable and uniquely identified.
    original_prepare=plugin.prepare
    def combined_prepare(*args,**kwargs):
        commit=original_prepare(*args,**kwargs)
        frontend=work/'drivers/AdrenoMetal/NativeBridgeMetalFrontend.mm'
        src=frontend.read_text()
        for needle,substitute in (
          (' dispatch_group_wait(_handlers,DISPATCH_TIME_FOREVER);',
           ' // Completion waits for execution, not queued callbacks.\n'
           ' // dispatch_group_wait(_handlers,DISPATCH_TIME_FOREVER);'),
          (' dispatch_group_wait(_schedulingHandlers,DISPATCH_TIME_FOREVER);',
           ' // Scheduled state must not wait for handler dispatch.\n'
           ' // dispatch_group_wait(_schedulingHandlers,DISPATCH_TIME_FOREVER);')
        ):
            if src.count(needle)!=1:
                raise RuntimeError('Combined wait patch source drift: '+needle)
            src=src.replace(needle,substitute,1)
        frontend.write_text(src)
        return commit
    plugin.prepare=combined_prepare
    report=plugin.build(work,device,out/'plugin',dict(os.environ),async_fix=True)
    report['completion_fix']=True
    report['combined_wait_fix']=True
    report['completion_patch_sha256']=sha((device/'patches/adrenometal-nabu-completion-wait.patch').read_bytes())
    (out/'plugin/plugin-report.json').write_text(json.dumps(report,indent=2)+'\n')

    assert report['bundle_built'] and report['plugin_returncode']==0
    assert report['async_fix'] is True and report['completion_fix'] is True and report['combined_wait_fix'] and report['async_creation']['passed']
    built=work/'build/adreno-metal-plugin';dest=out/'plugin/deployment-inputs';dest.mkdir()
    files=[]
    for name,expected in report['undeployed'].items():
        data=(built/name).read_bytes();assert sha(data)==expected
        shutil.copyfile(built/name,dest/name);files.append({'name':name,'sha256':expected,'bytes':len(data)})
    final={'status':'ASYNC_METAL_FRONTEND_HOST_PASS','async_cases':len(report['async_creation']['cases']),'files':files,'completion_wait_contract_preserved':False,'completion_deadlock_patch_applied':True,'hardware_tested':False,'boot_verified':False}
    (out/'plugin/async-fix-host-report.json').write_text(json.dumps(final,indent=2)+'\n')
    print(final['status'],final['async_cases'],flush=True)
if __name__=='__main__':main()
