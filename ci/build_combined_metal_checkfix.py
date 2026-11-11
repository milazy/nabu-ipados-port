"""Combined async + completion-wait plugin, plus handler-delivery waits in the frontend checks.

Device evidence (XNU2LOG sequence 1760, combined candidate installed 2026-11-10):
  M s0 c0 r0 i0 q167 k4/11 p15/8 F1 6607 the completed handler ru...
Check 7 read its completed-handler flag right after waitUntilCompleted. The
completion-wait fix (correctly) no longer makes waitUntilCompleted wait for
handler delivery, so the flag could still be false: one failed frontend check,
and NativeMetalBridgePhase.h gates GPU scanout on zero failed checks
(scanout = ok && frontendRan && !frontend.failed), hence offered=0 done=0.

This keeps both checks meaningful: each completed handler must still run, but
is given up to 2 s to be delivered asynchronously instead of being assumed
synchronous with waitUntilCompleted.
"""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_combined_metal_reuse as base

EDITS=(
 # check 6: handler order / status inside the completed handler
 ('            [cb addCompletedHandler:^(id<MTLCommandBuffer> c) {seen = c.status; done = order++;}];\n'
  '            if (finish(cb, "handlers")) {\n',
  '            dispatch_semaphore_t delivered6 = dispatch_semaphore_create(0);\n'
  '            [cb addCompletedHandler:^(id<MTLCommandBuffer> c) {seen = c.status; done = order++; dispatch_semaphore_signal(delivered6);}];\n'
  '            if (finish(cb, "handlers")) {\n'
  '                CHECK(!dispatch_semaphore_wait(delivered6, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC)), "completed handler not delivered within 2 s");\n'),
 # check 7: a failed command buffer still runs its completed handler
 ('            __block bool ran = false;\n'
  '            [cb addCompletedHandler:^(id<MTLCommandBuffer>) {ran = true;}];\n'
  '            [cb commit];\n'
  '            [cb waitUntilCompleted];\n',
  '            __block bool ran = false;\n'
  '            dispatch_semaphore_t delivered7 = dispatch_semaphore_create(0);\n'
  '            [cb addCompletedHandler:^(id<MTLCommandBuffer>) {ran = true; dispatch_semaphore_signal(delivered7);}];\n'
  '            [cb commit];\n'
  '            [cb waitUntilCompleted];\n'
  '            dispatch_semaphore_wait(delivered7, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC));\n'),
)

def apply_check_fix(checks:Path):
    src=checks.read_text()
    for old,new in EDITS:
        if src.count(old)!=1:raise RuntimeError('FrontendChecks.h source drift near: '+old.splitlines()[0].strip())
        src=src.replace(old,new,1)
    checks.write_text(src)
    return hashlib.sha256(src.encode()).hexdigest()

def main():
    # Wrap the plugin module's prepare once more: base.main() installs its own
    # wait patch wrapper on plugin.prepare, then calls plugin.build.
    applied={}
    def patch_plugin(mod):
        inner=mod.prepare
        def prepare(*a,**k):
            commit=inner(*a,**k)
            work=Path(a[0]) if a else Path(k['root'])
            applied['frontend_checks_sha256']=apply_check_fix(work/'drivers/AdrenoMetal/bridge/FrontendChecks.h')
            return commit
        mod.prepare=prepare
    # base.main imports nabu_metal_plugin_ci after inserting the device source-ci path;
    # hook its build() to install our wrapper on the already-wrapped prepare.
    import builtins
    real_imp=builtins.__import__
    def imp(name,*a,**k):
        m=real_imp(name,*a,**k)
        if name=='nabu_metal_plugin_ci' and not getattr(m,'_checkfix_hooked',False):
            m._checkfix_hooked=True
            build=m.build
            def wrapped(*ba,**bk):
                patch_plugin(m)
                rep=build(*ba,**bk)
                rep['frontend_checks_handler_wait']=True
                rep.update(applied)
                return rep
            m.build=wrapped
        return m
    builtins.__import__=imp
    try:base.main()
    finally:builtins.__import__=real_imp
    if not applied:raise RuntimeError('Frontend check fix was not applied')
    print('FRONTEND_CHECK_FIX_APPLIED',json.dumps(applied),flush=True)
if __name__=='__main__':main()
