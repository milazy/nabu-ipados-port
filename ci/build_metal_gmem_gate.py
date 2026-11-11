"""Checkfix Metal plugin, plus a boot-argument gate for Turnip's render mode.

AdrenoMetal (baad47c) sets TU_DEBUG to NATIVE_ADRENO_TURNIP_DEBUG = "sysmem,nocb" before Turnip starts. That
default came from the A740 stack; nabu's build defines no override, so every A640 pass renders straight to
system memory (DDR), the slowest mode on a tiler with a 1 MiB GMEM.

References on the same GPU and on the same stack:
  * sd855_ios26 (Adreno 640, iOS): TU_DEBUG=nocb, "on-chip GMEM tiling autotune without concurrent binning stalls".
  * UniXNU 01eb869 / e5f76cf (11 Nov 2026): "AdrenoMetal renders every pass in tile memory", GMEM is the default.
  * The reused Turnip (UniXNU cd2dd1b, 30 Oct 2026) already carries ed59941 "render unpadded host attachments in
    GMEM" and e038ba3 (owner-laid linear images at 64-byte pitch stay in SYSMEM).

The gate: when kern.bootargs contains "nabu-tu-gmem=1" the plugin sets TU_DEBUG=nocb (Turnip chooses GMEM or
SYSMEM per pass), otherwise the unchanged "sysmem,nocb". An existing TU_DEBUG still wins (setenv overwrite 0), and a
process that may not read kern.bootargs keeps the old default.
"""
import hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_combined_metal_checkfix as checkfix

OLD = '            setenv("TU_DEBUG", NATIVE_ADRENO_TURNIP_DEBUG, 0);\n'
NEW = ('            // NABU_TU_GMEM_GATE_V1: nabu-tu-gmem=1 lets Turnip render in GMEM (TU_DEBUG=nocb).\n'
       '            const char *nabuTuDebug = NATIVE_ADRENO_TURNIP_DEBUG;\n'
       '            {\n'
       '                char nabuArgs[1024] = {0};\n'
       '                size_t nabuLength = sizeof(nabuArgs) - 1;\n'
       '                if (!sysctlbyname("kern.bootargs", nabuArgs, &nabuLength, nullptr, 0) &&\n'
       '                    strstr(nabuArgs, "nabu-tu-gmem=1")) nabuTuDebug = "nocb";\n'
       '            }\n'
       '            setenv("TU_DEBUG", nabuTuDebug, 0);\n')
INCLUDE_OLD = '#include <pthread.h>\n'
INCLUDE_NEW = '#include <pthread.h>\n#include <sys/sysctl.h>\n#include <string.h>\n'
applied = {}


def gate(plugin: Path):
    src = plugin.read_text()
    for old, new in ((INCLUDE_OLD, INCLUDE_NEW), (OLD, NEW)):
        if src.count(old) != 1:
            raise RuntimeError('NativeAdrenoMetalPlugin.mm drift near: ' + old.strip())
        src = src.replace(old, new, 1)
    plugin.write_text(src)
    applied['nabu_tu_gmem_gate'] = True
    applied['plugin_source_sha256'] = hashlib.sha256(src.encode()).hexdigest()
    return applied['plugin_source_sha256']


inner_fix = checkfix.apply_check_fix


def apply_check_fix(checks: Path):
    digest = inner_fix(checks)
    gate(checks.parents[1] / 'NativeAdrenoMetalPlugin.mm')
    checkfix.applied_gate = dict(applied)
    return digest


checkfix.apply_check_fix = apply_check_fix

if __name__ == '__main__':
    checkfix.main()
    if not applied:
        raise RuntimeError('TU_DEBUG gate was not applied')
    # The checkfix report is written by build_combined_metal_reuse before our flag exists; add it.
    import json
    out = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
    report_path = out / 'plugin/plugin-report.json'
    report = json.loads(report_path.read_text())
    report.update(applied)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print('NABU_TU_GMEM_GATE_APPLIED', json.dumps(applied), flush=True)
