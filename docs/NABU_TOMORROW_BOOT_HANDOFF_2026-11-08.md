# Xiaomi Pad 5 → genuine iPadOS 17.7: next physical boot handoff

Prepared 2026-11-07 for the next owner session (2026-11-08). **Status: SOURCE + PREFLIGHT PREPARED; NOT FLASH-READY.**

## Work performed today

Private repository: https://github.com/giacomomilanesi/nabu-ipados-macos-build

- **Pinned public sources** in `ci/research_sources.lock.json`: main `zzweiqing/UniXNU-nabu` at `54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9`; Bergamota, HakiOS common XNU and HakiOS Xiaomi 15/dada are explicitly research-only.
- **Automated source-integrity audit**: `ci/audit_research_sources.py`, workflow `.github/workflows/prepare-nabu-flash-review.yml`. Verifies exact Git revision and specific files, and reports whether real 120Hz refresh/vsync code is still missing.
- **Release preflight**: `ci/audit_nabu_boot_candidate.py`, tests `tests/test_nabu_release_pipeline.py`. Requires all seven named artifact types with SHA256, a 4KB-aligned partition inventory and non-overlapping free allocations, plus a verified external source backup report. Its `ready_to_flash` value is **always false**: user approval and independent physical boot validation cannot be inferred by software.
- **120Hz/ProMotion audit**: `ci/qualify_nabu_promotion.py`, `tests/test_nabu_promotion.py`, and workflow `.github/workflows/qualify-nabu-promotion-120hz.yml`. 120Hz only becomes measurable after physical panel ID, real DSI/vblank events and functional iPadOS display driver. iPad Pro identity remains experimental and **has not been switched**.
- **Kernel build pin**: modified `.github/workflows/build-nabu-ufs-owner-root.yml` to fetch the exact advanced nabu revision before owner-root XNU build; triggered this workflow on its change. It builds a **kernel**, not a complete Apple OS installer.

### Observed GitHub workflow failures — no fake build success

All below were marked failure **before any step ran**; GitHub returns an empty `steps: []` and no runner name. We did not get actual compiler output, and cannot diagnose a source error from that data. GitHub Actions billing/usage/runner provisioning should be inspected on the web UI by the owner; no billing-setting change was performed.

- Source audit: https://github.com/giacomomilanesi/nabu-ipados-macos-build/actions/runs/42328040428
- Earlier ProMotion audit: https://github.com/giacomomilanesi/nabu-ipados-macos-build/actions/runs/42326691522
- Pinned full XNU owner-root kernel attempt: https://github.com/giacomomilanesi/nabu-ipados-macos-build/actions/runs/42328193717

No new bootable iPadOS image was produced. The Windows remote computer is offline as of the last check during KernelOS reinstallation, so the original Apple IPSW and physical disk could not be re-read.

## Next-session plan (in safe engineering order)

1. **Verify the backup before doing anything destructive.** On reconnected external F:, inspect `F:\NABU_IPADOS_COMPLETE_BACKUP_20261107\VERIFICATION_REPORT.json` and `BACKUP_COMPLETE_AND_VERIFIED.txt`. The previous copy contained 32,390 files / 40,374,431,865 bytes. It was size-complete, but cryptographic verification was still active at the end of the earlier interaction; do **not** assume it finished unless result=PASS and the marker exists. Keep `F:\NABU_IPADOS_RECOVERY_20261106` untouched.
2. Reconnect the PC and inspect GitHub Actions run annotations/billing (failed before job startup). Re-run only the source audit and owner-root kernel build after this is resolved. If GitHub runners remain unavailable, use a suitable macOS+Xcode host for the verified source build; don't call a failed CI red badge a compiler regression.
3. Extract the **user-owned** `iPad_10.2_17.7_21H16_Restore.ipsw` from the verified backup. Generate the pinned `ipsw-21h16-small.zip` via `zzweiqing/UniXNU-nabu/source-ci/prepare_ipsw_input.py`; confirm each Apple component hash and 21H16 `iPad7,11/j171ap` identity. Never commit Apple files, the owner's keys, or private partition images to public Git.
4. Build the actual source-pinned owner-root XNU kernel using existing `build-nabu-ufs-owner-root.yml`, the original OS+SystemOS owner policies, and Xcode. Verify `kernel.macho` is a valid ARM64 Mach-O, hashes and trust cache implementation. This alone does not imply iPadOS boots.
5. **Build the full OS/SystemOS root images, ADT, trust caches and UEFI payload**, not merely the kernel. The full iPadOS 17.7 Apple root volumes are **currently missing from the experimental boot menu**. Do not transplant the maintainer's fixed LBA / RAM map or Bergamota's Poco F1 boot.img without adapting to the owner hardware.
6. Collect/read-only GPT and DRAM map for the **owner's actual 128GB nabu**, select partition allocations that do not overlap Android `boot`, `super`, `userdata`, `cust`, `rescue`, or Qualcomm firmware. Candidate audit `ci/audit_nabu_boot_candidate.py` must pass using exact hashes and verified F: backup. A host-valid package is still **not approved for flashing**.
7. Prefer reversible **temporary Fastboot RAM boot** of a genuine, complete source-built candidate if compatible with actual loader. Log XNU, UFS root, `/sbin/launchd`, framebuffer, touch and SpringBoard. A colored bar, reset or UEFI menu is not success. Avoid burdening owner with repetitive low-signal boots.
8. Only after verified UI/root boot and restoration plan, present the exact destructive partition operation for explicit approval. **Never auto-flash / erase Android or userdata because a build succeeded**.

## Technical integration directions

- Primary nabu device port: https://github.com/zzweiqing/UniXNU-nabu
- Qualcomm loader, userland packaging / arm64e comparison: https://github.com/ry-diffusion/Bergamota
- HakiOS common XNU, `MiniIOMobileFramebuffer`, frame tracing, high rate app plist and native Metal: https://github.com/oosexgang/hakios-xnu-kernel
- iOS 26 Xiaomi 15 source, separate ISA research only: https://github.com/superboyyy/hakios-arm64e-dada
- iPadOS17 iPad Pro 10.5-inch `iPad7,3/j207ap` 120Hz ProMotion profile: **separate optional build; no board-id spoof on production baseline**. Validate full Apple IPSW and display ABI separately. iPadOS26 would require a newer Pro model; Android Qualcomm A860 lacks native PAC arm64e used on Xiaomi 15.

## 120Hz is required, but not currently working

Pad 5 physical panel supports 120Hz at 1600×2560. Its actual vendor variant must be identified. We have a nabu CSOT timing reference in Linux, but no evidence the 120Hz DSI mode is currently active under the proposed Apple UI. Pinned source `NabuLegacyDisplayProbe.cpp` contains no-op `native_legacy_vsync_notify` and `native_legacy_set_refresh_properties`. Need accurate native TE/vblank, IOKit properties, QuartzCore frame-rate capability, GPU swap completion and telemetry at real 8.33 ms. ProMotion identity alone is not sufficient.

## TrollStore, jailbreak-like environment and App Store

**TrollStore official version does NOT support 17.7**, only 17.0 and certain earlier versions: https://github.com/opa334/TrollStore . It uses patched CoreTrust vulnerabilities and is not a jailbreak. Also, the actual Xiaomi/Qualcomm boot ROM is not Apple's A10 boot ROM: an `iPad7,11` identity **does not make palera1n/checkm8 work** on the tablet.

A technically credible alternative, after native Apple userland boots, is to build a **custom signing/trust-policy and application-installation path** (possibly with `ldid`, suitable entitlements, `installd`/LaunchServices integration, OpenSSH, Procursus and Sileo), packaged from sources and owned private inputs. That is a custom developer/jailbreak-style environment, **not proof TrollStore itself runs**. Rootless package manager and filesystem access should be validated before installing third-party packages. Do not preinstall unknown IPA binaries or disable security on a network-accessible unfinished device without owner opt-in.

**App Store/Apple ID**: Apple authentication, device trust, activation, server attestation and networking remain major independent blockers. A custom userland with SpringBoard does not ensure Apple login or App Store purchases/downloads; no part of this workflow claims it. HakiOS common project explicitly doesn't support Apple services. Do not enter an Apple Account password or personal data on a research build whose platform security is intentionally relaxed.

## What is an actual successful next milestone?

Not a flashy screenshot; the device safely RAM-boots an owner-matched native kernel, validates the Apple OS + SystemOS root, starts launchd, and reaches a responsive SpringBoard with a recorded recovery path. Only then plan persistent installation. 120Hz, Wi-Fi, App Store and jailbreak-style package management each require separate evidence.
