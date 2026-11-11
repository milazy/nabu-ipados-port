"""A640 GPU clock and DDR vote above the fixed 257 MHz / 1.8 GB/s, behind a boot argument.

Measured on hardware (2026-11-11, seq 3328): GPU scanout completes at most about 8 frames per 10 ms-sampled second while
the user scrolls. The nabu GMU table offers exactly two GPU levels (off, 257 MHz LOW_SVS) and two DDR levels (off,
1799000 KB/s), and the perf vote picks level 1 / bandwidth 1. Every frame is composited in Turnip sysmem mode and copied
to the GOP scanout, so both the GPU clock and the DDR floor bound the frame rate.

Reference on the same GPU (Adreno 640, SM8150 RPMh): sd855_ios26 bsd/dev/sweet_a6xx.c gmu_hfi() sends the KGSL
hfi_dcvstable_cmd with the levels {0, 257000, 345000, 427000, 499200, 585000, 675000} kHz at RPMh ARC levels
{0, LOW_SVS 64, SVS 128, SVS_L1 192, SVS_L2 224, NOM 256, NOM_L1 320} and votes HFI_GX_BW_PERF_VOTE {1, level, bw}.
It runs iOS at 675 MHz on SM8150-AC (Snapdragon 855+/860, the nabu SoC). Xiaomi's nabu kernel (sm8150-v2.dtsi)
lists 700/675/585/427/... MHz GPU levels and DDR usecases up to 8363000 KB/s (usecase 10 = 7211000 KB/s).

nabu-gpu-level=N (2..6) adds GPU levels 2..N to the dcvs table, each only if command-db's gfx.lvl holds that exact ARC
level, adds a third DDR level at 7211000 KB/s (KGSL's live BCM conversion, same VCD grouping as level 1) and votes the
top GPU level with DDR level 2. If the GMU does not acknowledge that vote, the original {1, 1, 1} vote is sent.
Without the argument the tables and the vote are byte-identical to before.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
power = a.source / 'gpu/a640/NativeAdrenoA6xxPower.cpp'
gmu = a.source / 'gpu/a640/NativeAdrenoA6xxGmu.cpp'


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: %s (count %d)' % (what, text.count(old)))
    return text.replace(old, new, 1)


s = power.read_text()
s = once(s, '#include <IOKit/IOLib.h>\n', '#include <IOKit/IOLib.h>\n#include <pexpert/pexpert.h> // NABU_GPU_DVFS_V1\n',
         'power include')
s = once(s, '''    tables_.performance[52] = gmuVote;
    tables_.performance[53] = 200000;
''', '''    tables_.performance[52] = gmuVote;
    tables_.performance[53] = 200000;

    /* NABU_GPU_DVFS_V1: nabu-gpu-level=N adds KGSL's higher SM8150 GPU levels (sd855_ios26 sweet_a6xx.c). */
    unsigned dvfsTop = 0;
    if (!PE_parse_boot_argn("nabu-gpu-level", &dvfsTop, sizeof(dvfsTop)) || dvfsTop < 2 || dvfsTop > 6) {
        dvfsTop = 0;
    }
    if (dvfsTop) {
        static const uint32_t dvfsArc[7] = {0, 64, 128, 192, 224, 256, 320};
        static const uint32_t dvfsKhz[7] = {0, 257000, 345000, 427000, 499200, 585000, 675000};
        uint32_t previous = gpuVote;
        unsigned count = 2;
        for (unsigned level = 2; level <= dvfsTop; ++level) {
            uint32_t vote = 0;
            if (!arcVote(resources[0], resources[1], dvfsArc[level], &vote) ||
                (vote >> 16) != dvfsArc[level] || (vote & 0xff) <= (previous & 0xff)) {
                IOLog("NabuGPU DVFS: gfx.lvl has no ARC level %u; table stops at %u kHz\\n",
                    dvfsArc[level], dvfsKhz[count - 1]);
                break;
            }
            tables_.performance[2 + 3 * level] = vote;
            tables_.performance[3 + 3 * level] = 0xffffffff;
            tables_.performance[4 + 3 * level] = dvfsKhz[level];
            previous = vote;
            count = level + 1;
        }
        tables_.performance[0] = count;
        IOLog("NabuGPU DVFS: gpu levels=%u top=%u kHz vote=%08x\\n", count, dvfsKhz[count - 1], previous);
    }
''', 'performance table')
s = once(s, '''    unsigned ddr[3]={3,4,5},cnoc[3]={6,8,9};
    const uint32_t ddrWidths[3]={16,4,4},cnocWidths[3]={8,8,8};
    bandwidthGroup(ddr,ddrWidths,1799000,23,31,8,4);
''', '''    unsigned ddr[3]={3,4,5},cnoc[3]={6,8,9};
    const uint32_t ddrWidths[3]={16,4,4},cnocWidths[3]={8,8,8};
    if (dvfsTop) {
        /* Level 2 first: the group writes its level-0 row (commit bits only) at dataAt, which the
         * 1799000 KB/s call below then overwrites with level 1. */
        unsigned ddrHigh[3]={3,4,5};
        bandwidthGroup(ddrHigh,ddrWidths,7211000,23,39,8,4);
        tables_.bandwidth[0] = 3;
        IOLog("NabuGPU DVFS: DDR level 2 = 7211000 KB/s\\n");
    }
    bandwidthGroup(ddr,ddrWidths,1799000,23,31,8,4);
''', 'ddr bandwidth')
power.write_text(s)

g = gmu.read_text()
g = once(g, '''        config.tables->performance[0] != 2 || config.tables->performance[1] != 2 ||''',
         '''        config.tables->performance[0] < 2 || config.tables->performance[0] > 7 || // NABU_GPU_DVFS_V1
        config.tables->performance[1] != 2 ||''', 'gmu performance check')
g = once(g, '''        config.tables->bandwidth[0] != 2 || (config.chipId >> 16) != 0x0604) {''',
         '''        config.tables->bandwidth[0] < 2 || config.tables->bandwidth[0] > 3 ||
        (config.chipId >> 16) != 0x0604) {''', 'gmu bandwidth check')
g = once(g, '''    const uint32_t votePayload[] = {1, 1, 1};
    result = exchange(30, votePayload, 3);
    if (result) {
        return result;
    }
''', '''    const uint32_t votePayload[] = {1, config_.tables->performance[0] - 1, config_.tables->bandwidth[0] - 1};
    result = exchange(30, votePayload, 3);
    IOLog("NabuGPU DVFS: perf vote gpu=%u (%u kHz) bw=%u -> %x\\n", votePayload[1],
        config_.tables->performance[4 + 3 * votePayload[1]], votePayload[2], result);
    if (result && (votePayload[1] != 1 || votePayload[2] != 1)) {
        const uint32_t basePayload[] = {1, 1, 1};
        result = exchange(30, basePayload, 3);
        IOLog("NabuGPU DVFS: fallback perf vote 257000 kHz -> %x\\n", result);
    }
    if (result) {
        return result;
    }
''', 'perf vote')
gmu.write_text(g)
print('NABU_GPU_DVFS_V1 applied')
