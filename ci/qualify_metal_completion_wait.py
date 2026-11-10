"""Compile exact frontend wait methods with real dispatch and a bounded GPU stub."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
HARNESS=r'''
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
static dispatch_semaphore_t entered,releaseGpu,done;
static std::atomic<unsigned> calls{0};
static bool runtimeWait() {
 calls.fetch_add(1);dispatch_semaphore_signal(entered);
 return dispatch_semaphore_wait(releaseGpu,dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC))==0;
}
static void nmb_command_buffer_wait(void *,int) {if(!runtimeWait())exit(4);}
static bool nmb_command_buffer_wait_scheduled(void *) {return runtimeWait();}
static uint64_t nowUs(){return 0;}
struct Timer{void add(uint64_t){}};
static Timer gTimeWaitCompleted,gTimeWaitScheduled;
#define NBLOG(...) do {} while(0)
@interface NBWaitProbe:NSObject {
@public
 void *_handle;
 dispatch_group_t _handlers,_schedulingHandlers;
}
@property(nonatomic) BOOL committed,failedLocally;
- (void)waitUntilCompleted;
- (void)waitUntilScheduled;
@end
@implementation NBWaitProbe
__METHODS__
@end
static void require(bool ok,const char *why) {if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(2);}}
int main(int argc,char **argv) {@autoreleasepool {
 require(argc==3,"arguments");int kind=atoi(argv[1]),mode=atoi(argv[2]);
 NBWaitProbe *probe=[NBWaitProbe new];probe->_handle=(void *)1;
 probe->_handlers=dispatch_group_create();probe->_schedulingHandlers=dispatch_group_create();
 probe.committed=mode!=3;probe.failedLocally=mode==2;
 entered=dispatch_semaphore_create(0);releaseGpu=dispatch_semaphore_create(0);done=dispatch_semaphore_create(0);
 if(mode==1||mode==2){dispatch_group_enter(probe->_handlers);dispatch_group_enter(probe->_schedulingHandlers);}
 if(mode!=0)dispatch_semaphore_signal(releaseGpu);
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
  if(kind==0)[probe waitUntilCompleted];else [probe waitUntilScheduled];
  dispatch_semaphore_signal(done);
 });
 if(mode==0){
  require(dispatch_semaphore_wait(entered,dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC))==0,"runtime wait entered");
  require(dispatch_semaphore_wait(done,DISPATCH_TIME_NOW)!=0,"must wait for actual GPU execution");
  dispatch_semaphore_signal(releaseGpu);
 }
 require(dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC))==0,"callback delivery coupled to execution wait");
 require(calls.load()==((mode==0||mode==1)?1u:0u),"runtime wait count");
 if(mode==1||mode==2){dispatch_group_leave(probe->_handlers);dispatch_group_leave(probe->_schedulingHandlers);}
 printf("PASS completion kind=%d mode=%d\n",kind,mode);return 0;
}}
'''
def methods(source):
    result=[]
    for name in ('waitUntilCompleted','waitUntilScheduled'):
        marker='- (void)'+name+' {'
        assert source.count(marker)==1,'Method drift: '+name
        start=source.index(marker);end=source.index('\n}',start)+2
        result.append(source[start:end])
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline','fixed','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();assert sys.platform=='darwin' and os.environ.get('GITHUB_ACTIONS')=='true'
    a.output.mkdir(exist_ok=False)
    report={'hardware_tested':False,'gpu_exercised':False,'runtime_is_stub':True,'cases':[]}
    for variant,path in (('baseline',a.baseline),('fixed',a.fixed)):
        source=path.read_text();body=methods(source)
        report[variant+'_source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        report[variant+'_method_sha256']=[hashlib.sha256(x.encode()).hexdigest() for x in body]
        code=a.output/(variant+'.mm');code.write_text(HARNESS.replace('__METHODS__','\n'.join(body)))
        exe=a.output/variant
        command=['xcrun','clang++','-std=c++17','-fobjc-arc','-O1','-Wall','-Wextra','-Werror',str(code),'-framework','Foundation','-o',str(exe)]
        compiled=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (a.output/(variant+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
        assert compiled.returncode==0,'Harness compile failed: '+variant
        for kind in (0,1):
            for mode in range(4):
                run=subprocess.run([str(exe),str(kind),str(mode)],capture_output=True,text=True,timeout=8)
                expected_failure=variant=='baseline' and mode in (1,2)
                passed=(run.returncode==2 and 'FAIL callback delivery coupled to execution wait' in run.stderr) if expected_failure else (run.returncode==0 and run.stdout.startswith('PASS completion'))
                report['cases'].append(dict(variant=variant,kind=kind,mode=mode,returncode=run.returncode,passed=passed))
                (a.output/f'{variant}-{kind}-{mode}.log').write_text(run.stdout+run.stderr)
    report['passed']=all(x['passed'] for x in report['cases'])
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'],'Completion qualification failed'
    print('METAL_COMPLETION_WAIT_HOST_PASS',len(report['cases']))
if __name__=='__main__':main()
