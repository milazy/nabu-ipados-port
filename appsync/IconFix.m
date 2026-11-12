// SPDX-License-Identifier: MIT
// nabu: iconservicesagent renders app icons with CoreImage. On nabu (21H16) CoreImage picks its OpenGL ES path and crashes in
// CI::GLContext::init (NULL GL dispatch: no GL driver behind the Adreno Metal plugin), so every icon stays transparent.
// This library is loaded into a signed copy of iconservicesagent (routed through its Foundation dependency, like AppSync)
// and makes every CIContext the process creates a software one (kCIContextUseSoftwareRenderer). Nothing else changes.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <string.h>

static NSString *const kSoftware = @"kCIContextUseSoftwareRenderer";
static NSString *const kCacheIntermediates = @"kCIContextCacheIntermediates";

static NSDictionary *software(NSDictionary *options) {
    NSMutableDictionary *o = options ? [options mutableCopy] : [NSMutableDictionary dictionary];
    o[kSoftware] = @YES;
    o[kCacheIntermediates] = @NO;
    return o;
}

static id (*origInit)(id, SEL, NSDictionary *);
static id initWithOptions(id self, SEL cmd, NSDictionary *options) { return origInit(self, cmd, software(options)); }

static id (*origContextWithOptions)(id, SEL, NSDictionary *);
static id contextWithOptions(id self, SEL cmd, NSDictionary *options) {
    return origContextWithOptions(self, cmd, software(options));
}

// Any GL- or Metal-bound factory becomes a software context with the caller's options.
static id contextWithOptionsFallback(id self, NSDictionary *options) {
    SEL s = sel_registerName("contextWithOptions:");
    return ((id (*)(id, SEL, NSDictionary *))objc_msgSend)(self, s, software(options));
}
static id contextWithEAGL(id self, SEL cmd, id eagl) { return contextWithOptionsFallback(self, nil); }
static id contextWithEAGLOptions(id self, SEL cmd, id eagl, NSDictionary *o) { return contextWithOptionsFallback(self, o); }
static id contextWithMTL(id self, SEL cmd, id device) { return contextWithOptionsFallback(self, nil); }
static id contextWithMTLOptions(id self, SEL cmd, id device, NSDictionary *o) { return contextWithOptionsFallback(self, o); }

static void replace(Class cls, BOOL meta, const char *name, IMP imp, IMP *orig) {
    Class target = meta ? object_getClass(cls) : cls;
    Method m = class_getInstanceMethod(target, sel_registerName(name));
    if (!m) { NSLog(@"[nabu iconfix] %s missing", name); return; }
    IMP old = method_setImplementation(m, imp);
    if (orig) *orig = old;
    NSLog(@"[nabu iconfix] %s%s -> software", meta ? "+" : "-", name);
}

// Batch 6 showed iconservicesagent still crashing at pc 0 (NULL GL dispatch) through a path these CIContext hooks
// do not cover. Refusing every EAGLContext makes CoreImage's GL path fail cleanly instead of calling a NULL table.
static id eaglInitAPI(id self, SEL cmd, NSUInteger api) { return nil; }
static id eaglInitAPIShare(id self, SEL cmd, NSUInteger api, id group) { return nil; }

__attribute__((constructor)) static void start(void) {
    @autoreleasepool {
        dlopen("/System/Library/Frameworks/CoreImage.framework/CoreImage", RTLD_NOW);
        Class ci = objc_getClass("CIContext");
        if (!ci) { NSLog(@"[nabu iconfix] no CIContext; inactive"); return; }
        replace(ci, NO, "initWithOptions:", (IMP)initWithOptions, (IMP *)&origInit);
        replace(ci, YES, "contextWithOptions:", (IMP)contextWithOptions, (IMP *)&origContextWithOptions);
        replace(ci, YES, "contextWithEAGLContext:", (IMP)contextWithEAGL, NULL);
        replace(ci, YES, "contextWithEAGLContext:options:", (IMP)contextWithEAGLOptions, NULL);
        replace(ci, YES, "contextWithMTLDevice:", (IMP)contextWithMTL, NULL);
        replace(ci, YES, "contextWithMTLDevice:options:", (IMP)contextWithMTLOptions, NULL);
        dlopen("/System/Library/Frameworks/OpenGLES.framework/OpenGLES", RTLD_NOW);
        Class eagl = objc_getClass("EAGLContext");
        if (eagl) {
            replace(eagl, NO, "initWithAPI:", (IMP)eaglInitAPI, NULL);
            replace(eagl, NO, "initWithAPI:sharegroup:", (IMP)eaglInitAPIShare, NULL);
        }
        NSLog(@"[nabu iconfix] CoreImage contexts forced to software in %s", getprogname());
    }
}
