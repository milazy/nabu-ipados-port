# Standard compositor repair - 2026-11-10

Status: run 42738683958 is compiling the repair at kernel source commit `7b36b383c2a99541a59f291b6ec43754227a183f`. The tablet is in temporary recovery with the ESP block-read-only. No working UI is claimed.

## New device evidence

The preceding integrated rebuild ran behind the unchanged bootloader display. Recovery readback of `NABU_NEWEST_LOG_20261110T014038Z.bin` has SHA-256 `65116affb961a1cad8664528296e4133720e342332f9417250dbcedb9e89ccea`, CRC-verified committed sequence 558, boot ID `03bc751500000000ed01000000000000`. Its build timestamp and recorded arguments identify the preceding build and selected VSYNC/scanout settings. Apple startup and the GPU command-processor proof completed; the last display sample is at 120 seconds with zero accepted, transferred or retired frames. The snapshot is incomplete as a whole-boot record and does not establish a kernel hang.

The recorded arguments omit both addon activation switches. The kernel's standard `native_gpu_addon_prepare` returns immediately without `sheng-gpu-addon=1`. Thus publishing the kernel GPU accelerator did not install its user-space Metal bundle for compositor discovery. The preceding host checks qualified the kernel, but did not establish this addon startup path.

The installed addon is the standard eight-file `adrenoprobed` format, SHA-256 `8ff3cea1a75be938f10be7ba4f058db0b815157d8d1b15ab19d076fa620a8949`. It is not the closed `nabu-gpu-userprobe` format. The installed trust cache, SHA-256 `e654bec06ff2736c7dab81e8252eb8022f6ee9558d5156102fc7ae2321c2742b`, lacks the signed Metal bundle's CodeDirectory hash. The empty Data skeleton also lacks `/private/var/ngpu`, which the standard parent-directory helper assumes already exists.

## Consolidated correction

- Retain the exact standard addon and enable `sheng-gpu-addon=1` in the selected boot entry.
- Seed the root-owned `ngpu` directory before addon extraction; retain the source's corrected parent creation.
- Preserve the original trust-cache modules byte for byte and append one v2 module for the three exact existing owner executables. The resulting bundle SHA-256 is `0a5679e8a6d49228a4c9bda6b6b0363b50e96f74047847dbb943c3aa426739b5`.
- Compile the existing bounded UI observer and activate its callback independently of the closed addon transport. Runtime selects `nabu-ui-watch=1`; it does not select `nabu-gpu-userprobe=1`.
- Log standard addon extraction/mount results and the actual VSYNC timer counters. Retain the preceding VSYNC/GPU scanout implementation.

`ci/audit_compositor_transport.py` decodes the exact standard addon member set and verifies all signed code-page hashes and CodeDirectory hashes against the paired cache. All three executable inputs passed. This is static input validation, not evidence that the compositor works.

The generic source patch and the nabu source patch passed application checks against the pinned trees. The build workflow remains explicit dispatch only. A separate nine-entry closed-transport experiment was rejected locally as incompatible and must not be installed; the installed addon will remain unchanged.

## Installation boundary

`ci/prepare_standard_compositor.py` requires the new compiled backend/UI symbols, the matching postlink display-layout report and the audited signed addon/cache set before creating an owner-ZAP-adjusted image. The device installer stages all new and rollback inputs in RAM, preserves an independent fallback menu, checks each write and the protected payloads, then remounts the ESP block-read-only. Activation follows verified kernel/cache installation. A later accepted reboot command is still not proof of a visible UI.

OS/SystemOS, packed Data, ADT and the standard addon remain unchanged during this repair. Only the experimental kernel slot, its paired trust-cache sidecar and the selected menu entry are to change. Sustained visible SpringBoard and advancing presentation counters remain the decisive checks. Full App Store, networking, audio, persistent Data and 120 Hz operation remain unproven.
