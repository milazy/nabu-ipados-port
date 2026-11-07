# Bergamota review for genuine iPadOS 17.7 on Xiaomi Pad 5 (`nabu`)

Date: 2026-11-07. Source inspected: [ry-diffusion/Bergamota](https://github.com/ry-diffusion/Bergamota), default branch `develop`, last pushed 2026-10-26. This is a **fork** of [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet). The README claims original iOS 18.7.8 (22H352, iPhone XR) userland to SpringBoard on a Poco F1 (`beryllium`, Snapdragon 845, Adreno 630). Some subdocuments are earlier static-only engineering experiments; **claims of full physical runtime success should be independently verified**. This is **not** a nabu flash image or functional consumer iPadOS distribution.

## Recommendation

**Study Bergamota as a design/source reference while keeping `zzweiqing/UniXNU-nabu` as the main nabu-specific integration base.** Bergamota tackles boot handoff, Qualcomm hardware initialization, host-driven deployment, Apple userland packaging and host testing in ways that could shorten the nabu development effort. Do not use its `fastboot flash userdata`, `flash boot`, `logo`, hardcoded addresses, default boot configuration, or iOS 18 root on the owner's Pad 5.

## Useful subsystems, ordered by relevance

| Bergamota path | Reported implementation | Work for nabu |
|---|---|---|
| `enxerto/`: `README.md`, `loader.c`, `start.S`, `fdt.c`, `mmu*` | Bare-metal C/ASM loader launched as Android boot image from Qualcomm ABL. MMU on + cache maintenance, payload inflation, ADT handoff, error display | **High**: compare boot contract with current owner UEFI -> DarwinBoot handoff; consider host-only tests of payload memory placement, DTB/ADT validation and crash reporting. Not drop-in: nabu memory map, Android boot-image format and SoC differ |
| `enxerto/ufs.c`, `storage.c`, `sparse.c`; `docs/BERGAMOTA_FASTBOOT.md` | Fastboot-like USB with allowlisted raw/sparse storage access, block hashing and sparse/delta transfer, readback verification | **Medium-high**: adapt code/design for safer packaging and verification, **read-only until individually qualified**. Fastboot docs explicitly say the custom fastboot/UFS writing was **host-tested only, not exercised on hardware** at their documented stage. Never copy fixed UFS/SMMU memory addresses |
| `xnu/patches-11215/`, `xnu/patches-12377/`, `docs/XNU11215_MIGRATION.md` | Apple XNU modifications for Qualcomm SoC, PMIC, CPU/interrupts, storage, display, USB; iOS 18 kernel branch | **Medium**: audit patch patterns and problem-solving. Main nabu target is iPadOS 17.7 21H16; adapt semantically to correct pinned kernel, not wholesale cherry-picks of incompatible XNU versions |
| `tools/renegade/`: `mkroot-full.py`, `hfsx.py`, `img2simg.py`, `simg2img.py`, `root_tweaks18.py` | iOS root image creation, owners/permissions, Mach-O inventory, ad-hoc signing, first-boot service adaptations | **High as packaging reference**: implement read-only validation of OS/SystemOS contents, launchd dependencies, file ownership, trustcache and container layout against owner's original Apple IPSW. Bergamota's HFS+ root and modified signatures are architecturally different from native APFS owner-root source port |
| `tools/renegade/pacstrip.py`, `pacstrip_cache.py`; `docs/IOS18_PORT.md` | Rewrites arm64e/PAC instructions for Snapdragon 845, keeps instruction size, re-signs binaries and dyld shared cache | **Conditionally low** for current iPadOS 17.7 iPad7,11 (`j171ap`, A10-based, non-arm64e-era target). Do **not** run the blanket iOS 18 PAC stripping pipeline on 21H16. Audit actual binaries and only use technique if concrete ISA incompatibility is independently demonstrated |
| `tools/mkadt.py`, `tools/mkpayload.py`, `tools/extract-dtb.py` | Builds Apple Device Tree from original Qualcomm DTB + Apple's product identity; validates kernel handoff inputs | **High**: compare generated ADT properties with verified nabu 21H16 ADT, and compare real device DT memory/reservations to avoid early MMU faults |
| `docs/SSH_OVER_USB.md`, `enxerto/usb_dwc3.c`, `enxerto/usb_power.c` | Qualcomm USB with recovery/debug and key-only SSH over CDC-ECM | **Medium**: useful to replace colored-bar-only debug with host-readable boot logs, but DWC3 GDSCs/QUSB2/SMMU streams are SDM845-specific and require nabu register tracing |
| `gpu/`, `docs/GPU_A630_BRINGUP.md` | Adreno 630 GPU power/firmware/GMU/Firmware bringup | **Medium/low direct**: Ada 640 uses different firmware/clock/map and can only reuse overall initialization and fault-isolation methodology. Prefer nabu A640 driver source |

## Key architectural differences

- **Bergamota:** Poco F1 (Snapdragon 845 / Adreno 630), iPhone XR iOS 18.7.8 userland, XNU xnu-11215, Enxerto as boot.img via stock ABL, HFS+ root on Android `userdata`, binary patching to work around missing PAC. It warns that the port is experimental, erases Android user data, Apple security is mostly disabled, and many services do not work.
- **Our nabu source-based direction:** Xiaomi Pad 5 (Snapdragon 860 / SM8150-derived, Adreno 640), original iPadOS 17.7 build 21H16 iPad7,11 (`j171ap`), nabu-specific UniXNU patches, native UFS OS and SystemOS windows and original Apple OS volumes. Existing experimental image has `native-ufs-root=0` and **no OS volumes**; it cannot be repurposed into an installer.
- **Reference `zzweiqing/UniXNU-nabu`:** reports functioning XNU/UFS/CPU/touch/GPU/SpringBoard development, with persistent data and network/audio/power still incomplete; relies on maintainer-specific storage LBAs/DT mapping. Must independently reproduce and adapt without copying their free-space assumptions.

## Concrete host-only next steps for Codex

1. Clone Bergamota into a **new separate checkout** at a pinned commit, preserving existing owner's `UniXNU-nabu` modifications and backup. Record the upstream SHA and copy no Apple/proprietary payloads into Git.
2. Diff Enxerto's `loader.c` + `mmu*` + ADT handoff against nabu `DarwinBoot` and `board.toml`; make a checklist of exact entry register convention, cache maintenance, MMU, DT reservations and memory mappings.
3. Run/port its host-level bootloader and FAT/sparse/ADT verification tests to the **nabu image format** without touching the device. Add signature/arch inspection and checksums.
4. Audit the original 21H16 iPad7,11 Mach-O binaries and dyld shared cache to determine actual required ABI/ISA; don't assume iOS 18 arm64e adaptation is needed.
5. Adapt root packaging and launchd dependency checks to the existing nabu native OS/SystemOS/owner-root design; fail closed on missing Apple inputs, trustcache and UFS placement/partition overlap.
6. Compare DWC3/UFS/GPU initialization approaches at the *logic* level; do not reuse Bergamota SDM845 constants on nabu. Add host testable recovery and logging routines.
7. Compile source-built nabu kernel and a verified host-only EFI image. **No further repeated colored-bar boot tests, flash to Android userdata, boot or GPT modifications without separate evidence and explicit destructive approval.**
8. Record exactly which components are reused and which are incompatible; independently verify SpringBoard/Apple app claims before presenting any boot candidate as complete.

## Primary references

- https://github.com/ry-diffusion/Bergamota/blob/develop/README.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/enxerto/README.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/docs/BERGAMOTA_FASTBOOT.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/tools/renegade/README.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/docs/IOS18_PORT.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/docs/GPU_A630_BRINGUP.md
- https://github.com/ry-diffusion/Bergamota/blob/develop/docs/SSH_OVER_USB.md
