"""SM8150 CPU frequency: read the cpufreq-hw (OSM) tables and, on request, select each domain's top operating point.

Measured on hardware (2026-11-11, seq 3328): the desktop runs at about 20 frames per second. Nothing in the nabu kernel touches
the CPU frequency controller, so the cores stay wherever the boot firmware left them.

SM8150 facts (Linux arch/arm64/boot/dts/qcom/sm8150.dtsi, cpufreq_hw: qcom,cpufreq-hw):
  freq-domain0 0x18323000 (CPU0-3, Silver), freq-domain1 0x18325800 (CPU4-6, Gold), freq-domain2 0x18327800 (CPU7, Gold+),
  each 0x1400 bytes.
Register layout (Linux drivers/cpufreq/qcom-cpufreq-hw.c, qcom_soc_data for "qcom,cpufreq-hw"):
  reg_enable 0x0 (bit 0), reg_freq_lut 0x110 with 32-byte rows, reg_perf_state 0x920, at most 40 rows.
  LUT row: L_VAL bits 7:0, CORE_COUNT bits 18:16, SRC bits 31:30. SRC != 0: rate = 19.2 MHz * L_VAL; SRC == 0: 300 MHz (GPLL0/2).
  The table ends where a row repeats the previous rate (the repeat is the boost entry).

nabu-cpufreq=1 logs every domain's table and current index. nabu-cpufreq=2 also writes the last (highest) distinct index to
reg_perf_state, exactly as Linux's target_index does, and reads it back. The hardware limits management (LMh) still clamps the
frequency under thermal or current limits; this code does not touch it. Runs once, from the UI-watch writer at sample 2.
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
gen = a.source / 'scripts/nabu_ui_watch_source.py'
s = gen.read_text()


def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: %s (count %d)' % (what, text.count(old)))
    return text.replace(old, new, 1)


if 'NABU_CPUFREQ_V1' in s:
    raise SystemExit('cpufreq already applied')

FN = r'''/* NABU_CPUFREQ_V1: SM8150 cpufreq-hw tables, and the top operating point with nabu-cpufreq=2. */
extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern void delay(int usec);
static void
nabu_cpufreq_apply(void)
{
    unsigned mode = 0;
    if (!PE_parse_boot_argn("nabu-cpufreq", &mode, sizeof(mode)) || !mode) return;
    static const uint64_t bases[3] = {0x18323000ULL, 0x18325800ULL, 0x18327800ULL};
    for (unsigned d = 0; d < 3; ++d) {
        volatile uint32_t *r = (volatile uint32_t *)ml_io_map((vm_offset_t)bases[d], 0x1400);
        if (!r) { printf("NABU CPUFREQ d=%u map failed\n", d); continue; }
        const uint32_t enable = r[0];
        const uint32_t current = r[0x920 / 4];
        unsigned top = 0, rows = 0;
        uint32_t prev = 0, mhz[40];
        char line[240];
        int used = snprintf(line, sizeof(line), "NABU CPUFREQ d=%u en=%x cur=%u lut(MHz):", d, enable, current);
        for (unsigned i = 0; i < 40; ++i) {
            const uint32_t data = r[(0x110 + i * 32) / 4];
            const uint32_t src = (data >> 30) & 3, lval = data & 0xff;
            const uint32_t rate = src ? (19200u * lval) / 1000u : 300u;
            if (i && rate == prev) break;
            mhz[i] = rate;
            prev = rate;
            top = i;
            rows = i + 1;
            if (used > 0 && used < (int)sizeof(line) - 8)
                used += snprintf(line + used, sizeof(line) - (unsigned)used, " %u", rate);
        }
        printf("%s\n", line);
        if (mode == 2 && (enable & 1) && rows) {
            r[0x920 / 4] = top;
            __asm__ volatile("dsb sy" ::: "memory");
            delay(2000);
            printf("NABU CPUFREQ d=%u request=%u (%u MHz) readback=%u\n", d, top, mhz[top], r[0x920 / 4]);
        }
    }
}

'''

s = once(s, 'void\nnabu_ui_watch_snapshot(uint32_t out[6])\n', FN + 'void\nnabu_ui_watch_snapshot(uint32_t out[6])\n',
         'snapshot function')
s = once(s, '    const unsigned sample = ++nabu_ui_samples;\n',
         '    const unsigned sample = ++nabu_ui_samples;\n'
         '    if (sample == 2) nabu_cpufreq_apply();\n', 'sample counter')
gen.write_text(s)
print('NABU_CPUFREQ_PATCH_PASS', gen)
