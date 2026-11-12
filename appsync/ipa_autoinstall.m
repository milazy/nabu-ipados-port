// SPDX-License-Identifier: GPL-3.0-or-later
// nabu: install every IPA the PC dropped into /private/var/ngpu/ipa (GPU addon members ipa/*.ipa) through the
// AppSync-adapted installd, once per file content. Runs as a root launchd job from the owner launchd cache, with the
// same entitlements as unixnu-appinst (LSApplicationWorkspace installApplication:withOptions:error:).
// Results: /private/var/ngpu/ipa/<name>.done (or .failed with the error text), and kernel log lines "ipa: ..."
// through /dev/pmem when nabu-pmem=1. There is no shell on the device yet, so this is the IPA test path.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <CommonCrypto/CommonDigest.h>
#import <fcntl.h>
#import <sys/ioctl.h>
#import <sys/ioccom.h>
#import <unistd.h>

@interface NSObject (NabuInstall)
+ (id)defaultWorkspace;
- (BOOL)installApplication:(NSURL *)url withOptions:(NSDictionary *)options error:(NSError **)error;
@end

struct pmem_log { char text[240]; };
#define PMEM_LOG _IOW('P', 6, struct pmem_log)
#define DIR_IPA @"/private/var/ngpu/ipa"

static void say(NSString *text) {
    NSLog(@"[nabu ipa] %@", text);
    static int fd = -2;
    if (fd == -2) fd = open("/dev/pmem", O_RDWR);
    if (fd < 0) return;
    struct pmem_log line = {{0}};
    snprintf(line.text, sizeof(line.text), "ipa: %s", text.UTF8String);
    ioctl(fd, PMEM_LOG, &line);
}

static NSString *digest(NSString *path) {
    NSData *data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:NULL];
    if (!data) return nil;
    unsigned char out[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, out);
    NSMutableString *hex = [NSMutableString string];
    for (int i = 0; i < 8; ++i) [hex appendFormat:@"%02x", out[i]];
    return hex;
}

int main(void) {
    @autoreleasepool {
        say(@"started; waiting 45 s for SpringBoard and installd");
        sleep(45);  // let SpringBoard, installd and LaunchServices come up
        dlopen("/System/Library/Frameworks/CoreServices.framework/CoreServices", RTLD_NOW);
        Class cls = objc_getClass("LSApplicationWorkspace");
        id workspace = [cls respondsToSelector:@selector(defaultWorkspace)] ? [cls defaultWorkspace] : nil;
        if (![workspace respondsToSelector:@selector(installApplication:withOptions:error:)]) {
            say(@"LSApplicationWorkspace install SPI missing");
            return 3;
        }
        NSFileManager *files = NSFileManager.defaultManager;
        NSArray *names = [[files contentsOfDirectoryAtPath:DIR_IPA error:NULL] sortedArrayUsingSelector:@selector(compare:)];
        unsigned seen = 0, installed = 0, failed = 0;
        for (NSString *name in names) {
            if (![name.pathExtension.lowercaseString isEqual:@"ipa"]) continue;
            ++seen;
            NSString *path = [DIR_IPA stringByAppendingPathComponent:name];
            NSString *hash = digest(path);
            NSString *done = [path stringByAppendingFormat:@".%@.done", hash];
            if (!hash || [files fileExistsAtPath:done]) continue;
            NSString *work = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
            NSError *error = nil;
            BOOL ok = NO;
            if ([files createDirectoryAtPath:work withIntermediateDirectories:YES attributes:nil error:&error]) {
                NSString *copy = [work stringByAppendingPathComponent:@"install.ipa"];
                @try {
                    if ([files copyItemAtPath:path toPath:copy error:&error])
                        ok = [workspace installApplication:[NSURL fileURLWithPath:copy]
                                               withOptions:@{@"ApplicationType": @"User"} error:&error];
                } @catch (NSException *exception) {
                    error = [NSError errorWithDomain:@"nabu.ipa" code:1 userInfo:@{NSLocalizedDescriptionKey: exception.reason ?: @"exception"}];
                }
                [files removeItemAtPath:work error:NULL];
            }
            if (ok) {
                ++installed;
                [@"ok\n" writeToFile:done atomically:YES encoding:NSUTF8StringEncoding error:NULL];
                say([NSString stringWithFormat:@"installed %@ (%@)", name, hash]);
            } else {
                ++failed;
                NSString *why = error.description ?: @"unknown";
                [why writeToFile:[path stringByAppendingFormat:@".%@.failed", hash] atomically:YES encoding:NSUTF8StringEncoding error:NULL];
                say([NSString stringWithFormat:@"FAILED %@: %@", name, [why substringToIndex:MIN(why.length, (NSUInteger)180)]]);
            }
        }
        say([NSString stringWithFormat:@"done seen=%u installed=%u failed=%u", seen, installed, failed]);
        return failed ? 1 : 0;
    }
}
