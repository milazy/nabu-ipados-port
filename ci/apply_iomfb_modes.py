"""Publish truthful nabu GOP display timing and answer the current-mode IOMFB block.

Topaz 0948 demonstrates that a zero-filled selector-79 block leaves
CoreAnimation without a usable current display mode.  This patch is gated by
the existing nabu-iomfb-compat=1 flag.  It uses nabu's firmware-verified GOP
dimensions and the actual installed 60 Hz software VSYNC cadence.  It does not
assert Apple panel registers or invent a GPU implementation.
"""
import argparse
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--source",type=Path,required=True)
a=p.parse_args()

display=a.source/"platform/NabuLegacyCpuPresent.cpp"
s=display.read_text()
anchor='#include <libkern/c++/OSData.h>\n'
includes='#include <libkern/c++/OSData.h>\n#include <libkern/c++/OSNumber.h>\n#include <libkern/c++/OSArray.h>\n#include <libkern/c++/OSDictionary.h>\n#include <libkern/c++/OSBoolean.h>\n'
if s.count(anchor)!=1: raise SystemExit("Display header anchor mismatch")
s=s.replace(anchor,includes,1)

class_anchor='class NativeLegacyDisplay : public IOMobileFramebufferLegacy {\n    OSDeclareDefaultStructors(NativeLegacyDisplay)\n'
helper='''class NativeLegacyDisplay : public IOMobileFramebufferLegacy {
    OSDeclareDefaultStructors(NativeLegacyDisplay)
    static void nabuModeNumber(OSDictionary *dict, const char *name, uint32_t val) {
        OSNumber *value=OSNumber::withNumber(val,32);
        if(value) {dict->setObject(name,value);value->release();}
    }
    void publishNabuGopMode() {
        unsigned compat=0;PE_parse_boot_argn("nabu-iomfb-compat",&compat,sizeof(compat));
        if(compat!=1) return;
        uint32_t width=0,height=0;getDisplayDimensions(&width,&height);
        if(width<2 || height<2 || width>16384 || height>16384) return;
        OSDictionary *timing=OSDictionary::withCapacity(8);
        OSDictionary *horizontal=OSDictionary::withCapacity(4);
        OSDictionary *vertical=OSDictionary::withCapacity(4);
        OSDictionary *color=OSDictionary::withCapacity(8);
        OSArray *timings=OSArray::withCapacity(1);
        OSArray *colors=OSArray::withCapacity(1);
        if(timing && horizontal && vertical && color && timings && colors) {
            const uint32_t rate=60u<<16;
            nabuModeNumber(color,"ID",1);
            nabuModeNumber(color,"PixelEncoding",0);
            nabuModeNumber(color,"Depth",8);
            nabuModeNumber(color,"Colorimetry",1);
            nabuModeNumber(color,"EOTF",1);
            nabuModeNumber(color,"DynamicRange",0);
            nabuModeNumber(color,"Score",1);
            color->setObject("IsVirtual",kOSBooleanFalse);
            colors->setObject(color);
            nabuModeNumber(horizontal,"Active",width);
            nabuModeNumber(horizontal,"Total",width);
            nabuModeNumber(horizontal,"SyncRate",rate);
            nabuModeNumber(horizontal,"PreciseSyncRate",rate);
            nabuModeNumber(vertical,"Active",height);
            nabuModeNumber(vertical,"Total",height);
            nabuModeNumber(vertical,"SyncRate",rate);
            nabuModeNumber(vertical,"PreciseSyncRate",rate);
            nabuModeNumber(timing,"ID",1);
            nabuModeNumber(timing,"Score",1);
            timing->setObject("IsVirtual",kOSBooleanFalse);
            timing->setObject("IsOverscanned",kOSBooleanFalse);
            timing->setObject("HorizontalAttributes",horizontal);
            timing->setObject("VerticalAttributes",vertical);
            timing->setObject("ColorModes",colors);
            timings->setObject(timing);
            setProperty("TimingElements",timings);
            setProperty("ColorElements",colors);
            IOLog("NABU DISPLAY iomfb-modes published %ux%u rate=60/1 mode=1 color=1\\n",width,height);
        }
        OSSafeReleaseNULL(timings);
        OSSafeReleaseNULL(colors);
        OSSafeReleaseNULL(timing);
        OSSafeReleaseNULL(horizontal);
        OSSafeReleaseNULL(vertical);
        OSSafeReleaseNULL(color);
    }
'''
if s.count(class_anchor)!=1: raise SystemExit("Display class anchor mismatch")
s=s.replace(class_anchor,helper,1)
call_anchor='''            if (!startLogicalPM(provider)) {
                enabled = false;
                IOMobileFramebufferLegacy::stop(provider);
                return false;
            }
#if defined(NABU_LEGACY_GPU_SCANOUT)
'''
call_replacement='''            if (!startLogicalPM(provider)) {
                enabled = false;
                IOMobileFramebufferLegacy::stop(provider);
                return false;
            }
            publishNabuGopMode();
#if defined(NABU_LEGACY_GPU_SCANOUT)
'''
if s.count(call_anchor)!=1:raise SystemExit("Display call anchor mismatch")
s=s.replace(call_anchor,call_replacement,1)
display.write_text(s)

probe=a.source/"platform/NabuLegacyDisplayProbe.cpp"
s=probe.read_text()
anchor='''            if(args->structureOutputDescriptor==nullptr && args->structureOutput && args->structureOutputSize)
                bzero(args->structureOutput,args->structureOutputSize);
            status=kIOReturnSuccess;
'''
replacement='''            if(args->structureOutputDescriptor==nullptr && args->structureOutput && args->structureOutputSize)
                bzero(args->structureOutput,args->structureOutputSize);
            // IOMFB block 0x40 identifies the current timing and color mode.
            // A zero-filled current mode is not a valid display mode.
            if(selector==79 && args->structureOutputDescriptor==nullptr &&
               args->structureOutput && args->structureOutputSize>=12 &&
               args->scalarInput && args->scalarInputCount>=1 &&
               args->scalarInput[0]==0x40) {
                const uint32_t modeIds[2]={1,1};
                memcpy(reinterpret_cast<unsigned char *>(args->structureOutput)+4,modeIds,sizeof(modeIds));
                IOLog("NABU DISPLAY iomfb-mode block=0x40 color=1 timing=1\\n");
            }
            status=kIOReturnSuccess;
'''
if s.count(anchor)!=1:raise SystemExit("IOMFB compatibility shim anchor mismatch")
s=s.replace(anchor,replacement,1)
probe.write_text(s)
print("NABU_IOMFB_MODES_PATCH_PASS",display,probe)
