"""Apply a narrowly-scoped IOMobileFramebuffer user-client compatibility shim.

The current nabu 21H16 legacy framebuffer reaches backboardd, but optional setup
selectors return kIOReturnUnsupported before userspace ever submits SwapBegin/End.
A real Qualcomm iOS port (ios-topaz 0046) returns success with zeroed optional
outputs for these setup selectors.  Keep the original implementation first;
only backboardd, only with nabu-iomfb-compat=1, and only the observed failing
selectors may fall back.
"""
import argparse
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument("--source",type=Path,required=True)
a=p.parse_args()
f=a.source/"platform/NabuLegacyDisplayProbe.cpp"
s=f.read_text()
anchor="""    IOReturn status=stat?reinterpret_cast<ExternalFn>(stat->original_external)(client,selector,args,dispatch,target,ref):kIOReturnNotAttached;
    if(stat) {
"""
replacement="""    IOReturn status=stat?reinterpret_cast<ExternalFn>(stat->original_external)(client,selector,args,dispatch,target,ref):kIOReturnNotAttached;
    // 21H16 compatibility fallback, opt-in and process-scoped.  The original
    // user client remains authoritative.  Only setup selectors observed from
    // backboardd may convert an unsupported/generic optional operation into a
    // zero-valued success, matching the proven minimal AppleCLCD contract.
    unsigned iomfbCompat=0;
    (void)PE_parse_boot_argn("nabu-iomfb-compat",&iomfbCompat,sizeof(iomfbCompat));
    if(iomfbCompat==1 && stat && args && !strcmp(stat->name,"backboardd")) {
        bool eligible=false;
        switch(selector) {
        case 12: case 22: case 27: case 29: case 33:
        case 50: case 57: case 74: case 79: case 84:
            eligible=(status==kIOReturnUnsupported);break;
        case 15:
            eligible=(status==kIOReturnUnsupported || status==kIOReturnError);break;
        default: break;
        }
        if(eligible) {
            const uint32_t previous=(uint32_t)status;
            if(args->scalarOutput)
                for(uint32_t i=0;i<args->scalarOutputCount;++i)args->scalarOutput[i]=0;
            if(args->structureOutputDescriptor==nullptr && args->structureOutput && args->structureOutputSize)
                bzero(args->structureOutput,args->structureOutputSize);
            status=kIOReturnSuccess;
            IOLog("NABU DISPLAY iomfb-compat selector=%u previous=%08x in=%u/%u out=%u/%u\\n",
                selector,previous,args->scalarInputCount,args->structureInputSize,
                args->scalarOutputCount,args->structureOutputSize);
        }
    }
    if(stat) {
"""
if s.count(anchor)!=1: raise SystemExit("wrappedExternal anchor drift")
s=s.replace(anchor,replacement,1)
if s.count('nabu-iomfb-compat')!=1: raise SystemExit("compat insertion count mismatch")
f.write_text(s)
print("IOMFB_COMPAT_SOURCE_PATCH_PASS",f)
