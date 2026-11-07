# Research: Xiaomi 15 iOS 26 → Xiaomi Pad 5 nabu porting opportunities

Date: 2026-11-07. **Host/source-only research. No tablet writes or flash operations.**

## Origin and attribution

- [November 2, 2026 X post by @0x0SojalSec](https://x.com/0x0sojalsec/status/2117312872997179424) claims iOS 26 on Xiaomi 15, all App Store functions, a custom XNU kernel, a RAM-only Fastboot boot and publicly available source. The text was corroborated by searchable reposts; the original video could not be directly retrieved from X. **Do not equate this post with independently verified full system function.**
- A relevant **public source repository** exists for that device/OS: [superboyyy/hakios-arm64e-dada](https://github.com/superboyyy/hakios-arm64e-dada) (created Oct 30, last pushed Oct 31, default `main`). Its README reports iOS 26 22H??? userland, XNU `xnu-12377.121.6`, Snapdragon 8 Elite/SM8750 (codename `dada`), CPU with **native arm64e pointer authentication**, touchscreen, UFS-root, GPU Metal-to-Vulkan/Turnip, partial audio and Bluetooth; Liquid Glass shader translation requires additional debugging. Exact publication is not independent reproduction and the repo may not be the same physical demonstration as the X post.
- **Important discrepancy:** the developer's README says the iOS image lives in an **Android DSU partition**, not entirely in RAM. A RAM-only **loader** can be used while the OS root still lives on flash.
- **Apple services:** HakiOS FAQ https://hackios-web.vercel.app/en/faq explicitly says Apple ID and App Store sign-in *do not work and are not a goal*. Thus the viral claim that the App Store fully works is **unverified and contradicted by related HakiOS documentation**.
- Distinguish [7Night-kqx/UniXNU-dada](https://github.com/7Night-kqx/UniXNU-dada) (a separate Xiaomi 15 UniXNU device repository) from the above HakiOS fork: the UniXNU project reports UEFI operating but **UniXNU menu/XNU not yet run** in its own README. They are not interchangeable proofs.

## Actual published source candidates

| Code area | Public path | Relevance to nabu |
| --- | --- | --- |
| Core XNU patches | `kernel/xnu-12377.121.6-dada.patch` (~3.45 MB), `kernel/apply.sh` | Study arm64e adaptations, device/driver registration, Qualcomm initialization patterns. The patch is for iOS 26 XNU, **not** the owner's iPadOS 17.7 kernel; do not apply verbatim |
| Qualcomm EFI loader | `base/xnuloader`, `uefi-dada/uefi-dada.patch` | Compare image boot contract, handoff/cache/MMU and firmware boot assumptions with `UniXNU-nabu` and `DarwinBoot`; SM8750 hardware constants must not be copied |
| Apple userland initialization | `userland/` and `base/userland/` | Study launchd/daemon bootstrap and trustcache/entitlement handling, not Apple Account bypass claims |
| GPU | `gpu2/patches`, `gpu2/build_bridge.sh`, `gpu2/build_turnip_ios.sh`, `gpu2/build_plugin.sh` | Metal → Vulkan → Turnip approach is especially interesting for nabu Adreno 640. Compile against correct A640 GPU/GMU/SMMU paths, not A830 addresses |
| Storage | `base/tools` (dada setup/flash), UFS drivers in `kernel` | Host-only auditing of root volume staging, image verification, recovery; **never use fixed DSU/GPT regions from Xiaomi 15 on Pad 5** |

## Compatibility and roadmap

- Current owner's **nabu hardware**: Xiaomi Pad 5, Snapdragon 860 / SM8150-derived, Adreno 640, physical 120Hz 1600×2560 IPS; known experimental `cust` block 1GiB and Android userdata remain protected. Owner baseline is iPadOS 17.7 (21H16), `iPad7,11`/j171ap firmware, and the best nabu-specific source remains `zzweiqing/UniXNU-nabu`.
- **iOS/iPadOS 26 binary compatibility is a separate substantial workstream.** Xiaomi 15 Snapdragon 8 Elite has hardware PAC/arm64e; Pad 5's Snapdragon 860 does **not** supply the same native arm64e PAC execution. Reuse technique only after an ISA census of selected iPadOS 26 IPSW and evaluation of Bergamota's Renegade arm64e rewriting + real dyld/cache behavior. Never assume a clean firmware identity swap is sufficient.
- Apple officially supports **iPadOS 26 on iPad Pro 11-inch (1st generation, 2018) or later; iPad Pro 12.9-inch (3rd generation, 2018) or later.** The older 2017 iPad Pro 10.5-inch offers ProMotion for **iPadOS 17**, but not iPadOS 26. See https://support.apple.com/it-it/123706. Any proposed Apple profile needs its own IPSW BuildManifest, board/SoC/KernelCache, ADT and matching trustcache and power/display contracts.
- **120Hz / ProMotion**: panel-specific 60/120 hardware modes, real dual-DSI/TE/vblank interrupts, a functional `native_legacy_vsync_notify`, correct IOKit display refresh properties, GPU vsync/scanout timing and sustained device telemetry all must work. Do not count merely requesting 120Hz or advertising `ProMotion` as success. HakiOS FAQ says one phone reached around **107–118 fps** in a fast Metal path, but **not sustained 120**; this is not nabu evidence. The pinned `zzweiqing/UniXNU-nabu` `NabuLegacyDisplayProbe.cpp` still contains no-op refresh/vsync providers.
- A host-only fail-closed qualification audit and tests are committed to our repo: `ci/qualify_nabu_promotion.py`, `tests/test_nabu_promotion.py` and `.github/workflows/qualify-nabu-promotion-120hz.yml`. These do not implement actual display registers, and no physical 120Hz result has been claimed.
- For the physical nabu panel, Linux patch [nabu CSOT 120fps](https://github.com/Xander-trav/linux-nabu/blob/master/0025-drm-panel-nt36523-Enable-120fps-for-nabu-csot.patch) supplies timing formula `1768 * 2758 * 120 / 1000 = 585137.28 kHz` and admits a previous 104Hz stability workaround; different panels must be identified rather than hardcoding CSOT timing.

## Implementation directives

1. Pin and separately clone exact HakiOS dada and Bergamota revisions with **source-only** metadata; do not merge their device trees, firmware or flash scripts into the nabu default without review.
2. Keep **iPadOS 17.7 nabu** as the compile/boot target until launchd/SpringBoard and correct UFS root are real. Keep **iPadOS 26** behind a separate explicit profile/branch with independent IPSW input manifests and host-only build tests.
3. Integrate reusable **host-side** code: boot-image static assertions, ADT reserved-region checks, Mach-O ABI/ISA inventory, root-file/launchd checks, GPU userland dependencies, fail-closed UFS overlap validation and USB logging design.
4. For 120Hz, build real 60/120Hz kernel/display paths only after identifying the owner's physical panel. Clock, DSI synchronization, VSYNC timestamp telemetry, IOKit and GPU scanout need to be qualified independently.
5. Keep the user's recently copied F: recovery/archive intact. Never delete or overwrite project trees, private keys, or Apple system images. Any on-tablet erase, GPT rewrite or flash needs its own concrete rollback plan and explicit approval.
6. Never claim App Store/Apple Account operation, bootability, ProMotion 120Hz, or iPadOS 26 native operation unless reproduced and logged on the owner's actual Pad 5.

## Sources

- https://github.com/superboyyy/hakios-arm64e-dada
- https://github.com/7Night-kqx/UniXNU-dada
- https://hackios-web.vercel.app/en/faq
- https://github.com/ry-diffusion/Bergamota
- https://github.com/zzweiqing/UniXNU-nabu
- https://support.apple.com/it-it/123706
- https://github.com/Xander-trav/linux-nabu/blob/master/0025-drm-panel-nt36523-Enable-120fps-for-nabu-csot.patch
