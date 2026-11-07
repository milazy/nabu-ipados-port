# HakiOS common XNU kernel review — nabu integration and 120Hz

Date: November 7, 2026. Source-only research; no tablet or backup changes.

## What was verified

The repository https://github.com/oosexgang/hakios-xnu-kernel is the shared HakiOS kernel, loader, drivers and userland tooling (version 2.3.4, Apple XNU 8796.121.2, Darwin 22.5.0). It is NOT a ready-made iPadOS ROM for Xiaomi Pad 5. The documented physical device is a POCO X5 Pro (redwood, Qualcomm SM7325, Adreno 642L) via the separate hakios-sm7325 device port. The repository explicitly says Apple activation, Apple ID, iCloud and App Store services are not supported.

The source documents iOS/Darwin userland, kernel boot and graphics performance on redwood: reduced-resolution Settings scrolling reached about 118 fps and swipes 110-115 fps on its 120Hz panel. Full-resolution testing was slower. The maintainers explicitly state sustained 120 fps has not been reached. These are developer measurements, not evidence from nabu.

## Highest-priority reusable source

1. **Framebuffer and refresh negotiation** — https://github.com/oosexgang/hakios-xnu-kernel/blob/main/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp . Implements a timer-driven synthetic vsync, frame swaps, scanline-aware copy, timing and physical DPU register observations. Compare its IOKit selectors with nabu NabuLegacyCpuPresent.cpp and NabuLegacyDisplayProbe.cpp. It is based on iOS 16.5 and needs ABI review for iPadOS 17.7. Do not copy the SM7325 framebuffer register address.

2. **CoreAnimation/ProMotion diagnostics** — https://github.com/oosexgang/hakios-xnu-kernel/blob/main/userland/src/fps_info.m . Read-only inspection of CADisplay modes, UIScreen.maximumFramesPerSecond and MobileGestalt keys DeviceSupportsProMotion, DeviceSupports120HzRefreshRate, DeviceSupportsDynamicRefreshRate and MaxRefreshRate. Reimplement/compile against the target iPadOS 17.7 ABI; this helps distinguish iPad identity frame caps from actual panel rate.

3. **Per-app high-frame-rate opt-in** — https://github.com/oosexgang/hakios-xnu-kernel/blob/main/userland/mkhighrate.py . Alters Info.plist in a cloned root filesystem to add CADisableMinimumFrameDurationOnPhone. Their phone remained capped to 60 fps despite a 120Hz panel until userland opt-in. Because the property says OnPhone, its iPadOS 17 behavior is unknown. Do not modify original IPSW or stock system volumes. Verify effect on a separate candidate only.

4. **Frame pacing analysis** — https://github.com/oosexgang/hakios-xnu-kernel/blob/main/tools/frames.py . Separates frames affected by GPU wait, display copies, window-server idle and app gestures; records missed 8.33ms refresh intervals. Port methodology to nabu's kernel logs and actual vblank timestamps. Never report actual panel refresh based solely on CPU compositing numbers.

5. **Direct Metal renderer** — https://github.com/oosexgang/hakios-xnu-kernel/tree/main/hakios-metal . Alternative to metal2vulkan/Turnip for CoreAnimation. Existing backend refuses unknown Adreno chip IDs. Qualcomm Adreno 640 needs correct driver, GPU firmware, PM4, GMU, SMMU, clocks, cache rules, shader support and tests. Compare against the more advanced existing nabu A640/Turnip port.

6. **Boot, storage and porting** — docs/porting/index.md, docs/uefi-boot.md, drivers/storage/hakios.ufs.c and xnuloader/ . The generic UEFI-from-FAT32 path was verified in QEMU but explicitly not on phone. Never flash its loader or use redwood's DRAM/UFS assumptions on nabu.

## A practical nabu 120Hz roadmap

- Physical Xiaomi Pad 5 is 1600x2560 IPS with 120Hz support. Identify panel vendor/revision first; Linux nabu NT36523 patch 0025 (Xander-trav/linux-nabu) supplies a CSOT reference timing but cautions about earlier imperfect 120Hz stability.
- Add a real 60/120Hz physical DSI mode with bonded-DSI sync, TE/vblank interrupts, correct DPU clocks and 60Hz fail-safe. No direct SoC register writes until actual nabu hardware layout is validated.
- Replace no-op native_legacy_vsync_notify and native_legacy_set_refresh_properties in the pinned nabu display probe. Advertise true display mode and timestamped refresh events to CoreAnimation.
- Keep current iPad7,11/j171ap iPadOS 17.7 baseline working; investigate iPad7,3/j207ap iPad Pro 10.5-inch as a separately packaged ProMotion-capable 17.x candidate. It is NOT just a product-type substitution: kernelcache, BuildManifest, ADT, chip and board identity need independent validation.
- For userland frame caps, use fps_info and a read-only plist inventory first, then opt-in changes on disposable copies if needed. Validate true screen rate, frame presentation, UI fps, display tearing, heat and power individually.
- Our existing code ci/qualify_nabu_promotion.py and tests/test_nabu_promotion.py is an audit gate; it is NOT a display driver. Do not claim that committing it enabled ProMotion.
- Preserve Android, the local modified source checkouts and external F: backup. No repeated colored-bar tests or destructive device writes without a fully verified candidate and explicit permission.

## Source references

https://github.com/oosexgang/hakios-xnu-kernel/blob/main/README.md
https://github.com/oosexgang/hakios-xnu-kernel/blob/main/docs/reference/metal-measurements.md
https://github.com/oosexgang/hakios-xnu-kernel/blob/main/docs/reference/metal.md
https://github.com/oosexgang/hakios-xnu-kernel/blob/main/docs/porting/index.md
https://github.com/zzweiqing/UniXNU-nabu/blob/main/platform/NabuLegacyDisplayProbe.cpp
