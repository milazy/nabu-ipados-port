# Restore points on the ESP (12 Nov 2026)

Device: Xiaomi Pad 5 (nabu), serial 33288984, slot b. Android partitions untouched. ESP = /dev/block/sda29 (vfat),
files under /esp/EFI/UniXNU/. iPadOS is started with `fastboot boot MiPad5.UEFI-v2608.03_nSB.img` (RAM only; sha
f4d4ba55...). TWRP in RAM: V4-MODDED-TWRP-LINUX.img (sha 7a71da69...).

## RP-1: last build that reached Home + Safari + Settings (batch 1, installed 12 Nov 00:02)
Repository giacomomilanesi777-byte/nabu-ipados-macos-build, branch build/host-setup-20261111, commit ce3e212, CI run
43110582407; nabu source zzweiqing/UniXNU-nabu 54b4f98; UniXNU 245aca1a; XNU xnu-10063.141.1 (d8b8029); iPadOS 17.7 21H16.

| file (Payloads/ unless noted) | sha256 | backup suffix that restores it |
|---|---|---|
| kernel-fulltrace-panic.macho | d278caca36017e98959ff77500f2e84c67eae5f37d1a3b871dab9c7e818827a0 | .pre-batch2-20261112 |
| kernel-fulltrace-panic.macho.adt | ad6b53b7131900b4764dd6649d6ace425374cc3c06f4fb18cd67f6474fa4e772 | (unchanged by batch 2) |
| kernel-fulltrace-panic.macho.gpuaddon | 036f6714e8fbfa45fa2ffeacaa4f37e93b62c2047163d56cc77f9ae33324d103 | .pre-batch2-20261112 |
| kernel-fulltrace-panic.macho.trustcache | 496ac87e24ae207efe540ef01e49564ec863abfc249c57ce1c11bb5ade783efb | .pre-batch2-20261112 |
| ../unixnu.toml | 373ce4c6c873cff09ea4f29e2f3c05c3b24e891434ddb9754586ba262e2ea156 | .pre-batch2-20261112 |

Older: `.pre-batch1-20261111` (kernel 96d2d93f..., menu 4b0aacc9...), `.pre-combined-20261110` (addon/trust cache).

## Batch 2 (installed 12 Nov 00:46, hardware result pending)
Kernel from CI 43119267166 (prepared kernel-batch1.macho), addon f9ee94ad... (GMEM gate + clients), trust cache 36d9c1ee...,
menu 5538eed3... with two entries: `xnu-existing-ui-policy` FAST (default: nabu-gpu-level=5 nabu-tu-gmem=1
nabu-disable-watchdogd=2) and `xnu-batch2-safe` (RP-1 arguments on the batch-2 files).

## Restore procedure (TWRP, ESP only)
1. `fastboot boot V4-MODDED-TWRP-LINUX.img`.
2. `mount -t vfat -o rw /dev/block/sda29 /esp`; for each file: `cp F.pre-batch2-20261112 F`; check sha256 against the table; `umount /esp`.
3. `fastboot boot MiPad5.UEFI-v2608.03_nSB.img`.
Android is never modified; a normal reboot starts Android.
