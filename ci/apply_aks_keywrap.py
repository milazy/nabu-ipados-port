"""Port UniXNU AppleKeyStoreState software key wrapping (6ff4f11 / 5454637) to nabu's own AppleKeyStore.

Hardware evidence (XNU2LOG seq 2270, stacks symbolized against the 21H16 dyld cache):
- SpringBoard's main thread waits in a synchronous XPC reply from chronod (SBHIconManager init ->
  CHSWidgetExtensionProvider registerObserver: -> CHSChronoServicesConnection _subscribeToExtensions).
- chronod's main thread is inside ActivityKit initialisation; its IDS queue waits in dispatch_sync.
- liveactivitiesd waits on CoreDuet context and on IDSCopyLocalDeviceUniqueID (identityservicesd).
- nabu's AppleKeyStore answers selector 10 (aks_wrap_key) with kIOReturnUnsupported on every call
  ("NABU AKS sel=10 rc=0xe00002c7"), so keychain items cannot be created and IDS never finishes
  initialising.

UniXNU fixed exactly this on 2026-11-06 ("fix(keystore): wrap keys in software ... so the keychain can
store and read items"). nabu carries its own copy of the AppleKeyStore user client
(platform/NabuKeybagNotifications.cpp, based on AppleKeyStoreState 42ff83e), so the same selectors are
added here, byte-compatible with upstream:
  10 aks_wrap_key, 11 aks_unwrap_key, 23 aks_get_bag_uuid, 40 aks_generation, 160 aks_enable_cache_flow.

The device key derives from /chosen unique-chip-id when the device tree has a non-zero one, otherwise
from a fixed nabu label. nabu's Data volume is a RAM block recreated at every boot, so keychain items do
not outlive the boot either way. This is software wrapping, not hardware data protection.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
f = a.source / 'platform/NabuKeybagNotifications.cpp'
s = f.read_text()


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: %s (count %d)' % (what, text.count(old)))
    return text.replace(old, new, 1)


if 'NABU_AKS_KEYWRAP_V1' in s:
    raise SystemExit('key wrapping already applied')

s = once(s, '#include <IOKit/IOLib.h>\n',
         '#include <IOKit/IOLib.h>\n#include <IOKit/IODeviceTreeSupport.h>\n#include <libkern/c++/OSData.h>\n',
         'includes')

s = once(s, 'constexpr uint32_t kSelLockState = 7, kSelGetSystem = 14, kSelDeviceState = 17, kSelExtendedDeviceState = 35;\n',
         'constexpr uint32_t kSelLockState = 7, kSelGetSystem = 14, kSelDeviceState = 17, kSelExtendedDeviceState = 35;\n'
         '// NABU_AKS_KEYWRAP_V1: software key wrapping, ported from UniXNU AppleKeyStoreState 6ff4f11.\n'
         'constexpr uint32_t kSelWrapKey = 10, kSelUnwrapKey = 11, kSelBagUuid = 23, kSelGeneration = 40, kSelCacheFlow = 160;\n'
         'constexpr size_t kTagBytes = 8, kMaxKeyBytes = 256;\n',
         'selector constants')

HELPERS = r'''
// Self-contained so wrapping does not depend on when the kernel's crypto provider registers.
class Sha256 {
    uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    uint8_t buffer[64];
    uint64_t total = 0;
    size_t fill = 0;
    static uint32_t rotate(uint32_t v, unsigned n) { return (v >> n) | (v << (32 - n)); }
    void block(const uint8_t *p) {
        static const uint32_t k[64] = {
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
        uint32_t w[64];
        for (unsigned i = 0; i < 16; ++i)
            w[i] = (uint32_t)p[i * 4] << 24 | (uint32_t)p[i * 4 + 1] << 16 | (uint32_t)p[i * 4 + 2] << 8 | p[i * 4 + 3];
        for (unsigned i = 16; i < 64; ++i) {
            uint32_t s0 = rotate(w[i - 15], 7) ^ rotate(w[i - 15], 18) ^ (w[i - 15] >> 3);
            uint32_t s1 = rotate(w[i - 2], 17) ^ rotate(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t s[8];
        for (unsigned i = 0; i < 8; ++i) s[i] = h[i];
        for (unsigned i = 0; i < 64; ++i) {
            uint32_t t1 = s[7] + (rotate(s[4], 6) ^ rotate(s[4], 11) ^ rotate(s[4], 25)) +
                          ((s[4] & s[5]) ^ (~s[4] & s[6])) + k[i] + w[i];
            uint32_t t2 = (rotate(s[0], 2) ^ rotate(s[0], 13) ^ rotate(s[0], 22)) +
                          ((s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]));
            for (unsigned j = 7; j > 0; --j) s[j] = s[j - 1];
            s[4] += t1;
            s[0] = t1 + t2;
        }
        for (unsigned i = 0; i < 8; ++i) h[i] += s[i];
    }
public:
    void update(const void *data, size_t n) {
        const uint8_t *p = (const uint8_t *)data;
        total += n;
        while (n) {
            if (!fill && n >= sizeof buffer) { block(p); p += sizeof buffer; n -= sizeof buffer; continue; }
            size_t take = sizeof buffer - fill < n ? sizeof buffer - fill : n;
            for (size_t i = 0; i < take; ++i) buffer[fill + i] = p[i];
            fill += take; p += take; n -= take;
            if (fill == sizeof buffer) { block(buffer); fill = 0; }
        }
    }
    void final(uint8_t out[32]) {
        uint64_t bits = total * 8;
        const uint8_t one = 0x80, zero = 0;
        update(&one, 1);
        while (fill != 56) update(&zero, 1);
        uint8_t length[8];
        for (unsigned i = 0; i < 8; ++i) length[i] = (uint8_t)(bits >> (56 - 8 * i));
        update(length, 8);
        for (unsigned i = 0; i < 8; ++i)
            for (unsigned j = 0; j < 4; ++j) out[i * 4 + j] = (uint8_t)(h[i] >> (24 - 8 * j));
    }
};

// /chosen unique-chip-id when present and non-zero; otherwise a fixed label (the RAM Data volume is
// recreated at every boot, so no keychain item outlives the key either way).
size_t nabuDeviceId(uint8_t *out, size_t capacity)
{
    IORegistryEntry *chosen = IORegistryEntry::fromPath("/chosen", gIODTPlane);
    OSData *id = chosen ? OSDynamicCast(OSData, chosen->getProperty("unique-chip-id")) : nullptr;
    size_t n = 0;
    if (id && id->getLength() >= 8 && id->getLength() <= capacity) {
        const uint8_t *bytes = static_cast<const uint8_t *>(id->getBytesNoCopy());
        bool nonzero = false;
        for (unsigned i = 0; i < id->getLength(); ++i) { out[i] = bytes[i]; nonzero |= bytes[i] != 0; }
        if (nonzero) n = id->getLength();
    }
    if (chosen) chosen->release();
    if (!n) {
        static const char label[] = "nabu ram-data keystore";
        n = sizeof label - 1 < capacity ? sizeof label - 1 : capacity;
        for (size_t i = 0; i < n; ++i) out[i] = (uint8_t)label[i];
    }
    return n;
}
bool deviceKey(uint8_t key[32])
{
    static uint8_t cached[32];
    static volatile bool ready;
    if (!ready) {
        uint8_t id[32];
        size_t n = nabuDeviceId(id, sizeof id);
        if (!n) return false;
        static const char domain[] = "UniXNU AppleKeyStore v1";
        Sha256 hash;
        hash.update(domain, sizeof domain - 1);
        hash.update(id, n);
        hash.final(cached);
        ready = true;
    }
    for (unsigned i = 0; i < 32; ++i) key[i] = cached[i];
    return true;
}
void wrapTag(const uint8_t key[32], const uint8_t *plain, size_t n, uint8_t tag[kTagBytes])
{
    uint8_t digest[32];
    const uint8_t label = 'T';
    Sha256 hash;
    hash.update(key, 32); hash.update(&label, 1); hash.update(plain, n); hash.final(digest);
    for (size_t i = 0; i < kTagBytes; ++i) tag[i] = digest[i];
}
void wrapStream(const uint8_t key[32], const uint8_t tag[kTagBytes], const uint8_t *in, uint8_t *out, size_t n)
{
    const uint8_t label = 'S';
    for (size_t at = 0; at < n; at += 32) {
        uint8_t counter[4] = {(uint8_t)(at >> 5), (uint8_t)(at >> 13), (uint8_t)(at >> 21), (uint8_t)(at >> 29)};
        uint8_t digest[32];
        Sha256 hash;
        hash.update(key, 32); hash.update(&label, 1); hash.update(tag, kTagBytes); hash.update(counter, 4);
        hash.final(digest);
        for (size_t i = 0; i < 32 && at + i < n; ++i) out[at + i] = in[at + i] ^ digest[i];
    }
}
IOReturn writeOutput(IOExternalMethodArguments *args, const uint8_t *data, size_t n)
{
    if (args->structureOutputDescriptor) {
        if (n > args->structureOutputDescriptor->getLength()) return kIOReturnNoSpace;
        args->structureOutputDescriptor->writeBytes(0, data, n);
        args->structureOutputDescriptorSize = (uint32_t)n;
        return kIOReturnSuccess;
    }
    if (!args->structureOutput || n > args->structureOutputSize) return kIOReturnNoSpace;
    for (size_t i = 0; i < n; ++i) ((uint8_t *)args->structureOutput)[i] = data[i];
    args->structureOutputSize = (uint32_t)n;
    return kIOReturnSuccess;
}
IOReturn wrapKey(IOExternalMethodArguments *args)
{
    size_t n = args->structureInputSize;
    if (args->scalarInputCount != 2 || !args->scalarOutput || args->scalarOutputCount != 1 || !args->structureInput ||
        !n || n > kMaxKeyBytes) return kIOReturnBadArgument;
    uint8_t key[32], blob[kTagBytes + kMaxKeyBytes];
    if (!deviceKey(key)) return kAksError;
    wrapTag(key, (const uint8_t *)args->structureInput, n, blob);
    wrapStream(key, blob, (const uint8_t *)args->structureInput, blob + kTagBytes, n);
    IOReturn rc = writeOutput(args, blob, kTagBytes + n);
    if (rc == kIOReturnSuccess) args->scalarOutput[0] = args->scalarInput[1];
    return rc;
}
IOReturn unwrapKey(IOExternalMethodArguments *args)
{
    size_t n = args->structureInputSize;
    if (args->scalarInputCount != 2 || args->scalarOutputCount != 0 || !args->structureInput ||
        n <= kTagBytes || n > kTagBytes + kMaxKeyBytes) return kIOReturnBadArgument;
    uint8_t key[32], plain[kMaxKeyBytes], tag[kTagBytes];
    if (!deviceKey(key)) return kAksError;
    const uint8_t *blob = (const uint8_t *)args->structureInput;
    n -= kTagBytes;
    wrapStream(key, blob, blob + kTagBytes, plain, n);
    wrapTag(key, plain, n, tag);
    uint8_t difference = 0;
    for (size_t i = 0; i < kTagBytes; ++i) difference |= (uint8_t)(tag[i] ^ blob[i]);
    return difference ? kAksError : writeOutput(args, plain, n);
}
IOReturn bagUuid(IOExternalMethodArguments *args)
{
    uint8_t key[32], digest[32];
    if (!deviceKey(key)) return kAksError;
    const uint8_t label = 'U';
    Sha256 hash;
    hash.update(key, 32); hash.update(&label, 1); hash.final(digest);
    args->scalarOutputCount = 0;
    return writeOutput(args, digest, 16);
}
}  // namespace
'''
s = once(s, '}  // namespace\n', HELPERS.lstrip('\n'), 'namespace end')

s = once(s, '        case 0: case 4: case 5: case 9: case 12: case 13: case 26: case 27: case 55: case 101: case 102:\n',
         '        case 0: case 4: case 5: case 9: case 12: case 13: case 26: case 27: case 55: case 101: case 102: case kSelCacheFlow:\n',
         'no-output selectors')
s = once(s, '''        default: break;
        }
        uint32_t calls = ++nabu_aks_state_calls;''', '''        case kSelWrapKey: rc = wrapKey(args); break;
        case kSelUnwrapKey: rc = unwrapKey(args); break;
        case kSelBagUuid: rc = bagUuid(args); break;
        case kSelGeneration:
            if (args->scalarInputCount != 2 || !args->scalarOutput || args->scalarOutputCount != 1) { rc = kIOReturnBadArgument; break; }
            args->scalarOutput[0] = 0;
            rc = kIOReturnSuccess;
            break;
        default: break;
        }
        uint32_t calls = ++nabu_aks_state_calls;''', 'key selectors')
s = once(s, 'if (calls <= 48) IOLog("NABU AKS sel=%u rc=%#x\\n", selector, (unsigned)rc);',
         'if (calls <= 96 || (rc && calls <= 400)) IOLog("NABU AKS sel=%u rc=%#x\\n", selector, (unsigned)rc);', 'log bound')
s = once(s, '!setProperty("KeyOperationsAvailable", false)', '!setProperty("KeyOperationsAvailable", aksStateEnabled())',
         'key operations property')
f.write_text(s)
print('NABU_AKS_KEYWRAP_PATCH_PASS', f)
