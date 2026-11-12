"""Per-frame display timing for the GOP scanout hand-off (NABU_FRAME_TIMING_V1).

The 10-second writer_scanout counters (offered/done) cannot separate rendering from presentation. This adds, in
platform/NabuGpuScanoutHandoff.h, mach_absolute_time stamps at offer (compositor swap reaches the kernel), delivery
(the GPU copy client takes the frame) and completion (copy to the panel finished), and counts swaps refused because the
previous frame was still in flight (dropped frames). NativeAdrenoService prints one extra line per sample:

  NabuGPU: writer_frames=S n=N busy=B wait_avg/max=..us copy_avg/max=..us gap<12/<20/<28/<40/<70/>=70ms=a/b/c/d/e/f

gap is the interval between consecutive offers: about 8 ms at 120 Hz, 16.7 ms at 60 Hz. wait is offer -> delivery
(the copy thread was late), copy is delivery -> completion (GPU copy to the scanout). The numbers are cumulative.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
h = a.source / 'platform/NabuGpuScanoutHandoff.h'
s = a.source / 'gpu/a640/NativeAdrenoService.cpp'


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: %s (count %d)' % (what, text.count(old)))
    return text.replace(old, new, 1)


t = h.read_text()
t = once(t, 'volatile uint32_t nabu_scanout_ready,nabu_scanout_last_status,nabu_scanout_pending;\n}\n',
         'volatile uint32_t nabu_scanout_ready,nabu_scanout_last_status,nabu_scanout_pending;\n'
         '/* NABU_FRAME_TIMING_V1 */\n'
         'volatile uint64_t nabu_frame_n,nabu_frame_busy,nabu_frame_wait_sum,nabu_frame_wait_max,nabu_frame_copy_sum,nabu_frame_copy_max;\n'
         'volatile uint64_t nabu_frame_gap[6];\n'
         '}\n'
         'static uint64_t nabu_frame_offer_at,nabu_frame_deliver_at,nabu_frame_last_offer;\n'
         'static inline uint64_t nabu_frame_us(uint64_t delta){uint64_t ns=0;absolutetime_to_nanoseconds(delta,&ns);return ns/1000;}\n',
         'globals')
t = once(t, '            ++nabu_scanout_offers;nabu_scanout_pending=1;IOLockWakeup(gate_,&offered_,false);\n        }\n',
         '            ++nabu_scanout_offers;nabu_scanout_pending=1;IOLockWakeup(gate_,&offered_,false);\n'
         '            const uint64_t now=mach_absolute_time();\n'
         '            if(nabu_frame_last_offer){const uint64_t gap=nabu_frame_us(now-nabu_frame_last_offer);\n'
         '                ++nabu_frame_gap[gap<12000?0:gap<20000?1:gap<28000?2:gap<40000?3:gap<70000?4:5];}\n'
         '            nabu_frame_last_offer=now;nabu_frame_offer_at=now;\n'
         '        } else if(online_ && client_ && offered_) {\n'
         '            ++nabu_frame_busy;\n'
         '        }\n', 'offer')
t = once(t, '            delivered_=true;\n            NGPSwap swap=',
         '            delivered_=true;\n'
         '            {const uint64_t now=mach_absolute_time();nabu_frame_deliver_at=now;\n'
         '             const uint64_t w=nabu_frame_offer_at?nabu_frame_us(now-nabu_frame_offer_at):0;\n'
         '             nabu_frame_wait_sum+=w;if(w>nabu_frame_wait_max)nabu_frame_wait_max=w;}\n'
         '            NGPSwap swap=', 'deliver')
t = once(t, '            else ++nabu_scanout_completed;\n',
         '            else {++nabu_scanout_completed;\n'
         '                const uint64_t c=nabu_frame_deliver_at?nabu_frame_us(mach_absolute_time()-nabu_frame_deliver_at):0;\n'
         '                ++nabu_frame_n;nabu_frame_copy_sum+=c;if(c>nabu_frame_copy_max)nabu_frame_copy_max=c;}\n', 'complete')
h.write_text(t)

u = s.read_text()
u = once(u, 'extern volatile uint32_t nabu_scanout_ready,nabu_scanout_last_status,nabu_scanout_pending;\n',
         'extern volatile uint32_t nabu_scanout_ready,nabu_scanout_last_status,nabu_scanout_pending;\n'
         'extern volatile uint64_t nabu_frame_n,nabu_frame_busy,nabu_frame_wait_sum,nabu_frame_wait_max,nabu_frame_copy_sum,nabu_frame_copy_max;\n'
         'extern volatile uint64_t nabu_frame_gap[6];\n', 'service externs')
u = once(u, '''    emit(snprintf(line,sizeof(line),
        "NabuGPU: writer_scanout_wait=%u''', '''    {
        const unsigned long long n=nabu_frame_n?nabu_frame_n:1;
        emit(snprintf(line,sizeof(line),
            "NabuGPU: writer_frames=%u n=%llu busy=%llu wait_avg/max=%llu/%lluus copy_avg/max=%llu/%lluus "
            "gap<12/<20/<28/<40/<70/>=70ms=%llu/%llu/%llu/%llu/%llu/%llu\\n",
            sample,static_cast<unsigned long long>(nabu_frame_n),static_cast<unsigned long long>(nabu_frame_busy),
            static_cast<unsigned long long>(nabu_frame_wait_sum)/n,static_cast<unsigned long long>(nabu_frame_wait_max),
            static_cast<unsigned long long>(nabu_frame_copy_sum)/n,static_cast<unsigned long long>(nabu_frame_copy_max),
            static_cast<unsigned long long>(nabu_frame_gap[0]),static_cast<unsigned long long>(nabu_frame_gap[1]),
            static_cast<unsigned long long>(nabu_frame_gap[2]),static_cast<unsigned long long>(nabu_frame_gap[3]),
            static_cast<unsigned long long>(nabu_frame_gap[4]),static_cast<unsigned long long>(nabu_frame_gap[5])));
    }
    emit(snprintf(line,sizeof(line),
        "NabuGPU: writer_scanout_wait=%u''', 'service print')
s.write_text(u)
print('NABU_FRAME_TIMING_V1 applied')
