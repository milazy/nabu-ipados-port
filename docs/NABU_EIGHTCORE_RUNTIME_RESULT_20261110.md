# Nabu eight-core runtime result — 2026-11-10

## Outcome
**Partial hardware bring-up only; no graphical iPadOS session. Do not label this build boot-complete.**

- Latest test: UEFI RAM boot from the eight-core ADT/menu installation (kernel SHA-256 `7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d`).
- Installed ADT SHA-256: `429d9e7f39da10fb373b4a05081b9817843fe6c8e86e10728ac8fb74f7fbb514`.
- Log pulled in read-only TWRP from `/esp/XNU2LOG.BIN`; CRC verified, sequence 1420; local report at `reports/eightcore-postboot-20261110T1636/boot-log.txt`.
- All eight cores active: `ncpus=8 avail=8 topo=8`; seven secondary cores `step=7 fail=0 psci=0`, timer and SGI counters increase. This resolves the previous one-core configuration.
- SpringBoard, backboardd and runningboardd are observed alive in the boot log.
- IOMFB 1600x2560/60Hz mode published; optional compatibility selector calls run.
- **Still zero displayed frames:** `NABU DISPLAY swaps accepted=0`, `writer_scanout offered=0 done=0`, `render_proof=0`. The physical display retains the old UEFI menu and diagnostic green bar.
- `writer_exec attempts=0`; GPU self-test rows show `Compile(NeedsInput(TileAttachments))`, but these are offline self-test results, not proof of the actual compositor's failure mechanism.
- No additional flash is justified by the current evidence. Need a live renderer/userland submit-path diagnosis or independently validated complete release before another attempt.

## Safe fallback
The Android dynamic `system_b` partition still mounts read-only in TWRP and contains an Android system/app tree; `ro.build.version.release=16`. The current `boot_a` image matches the November 6 verified backup; `boot_b` differs, so do not assume a normal boot will work or switch slots blindly. Verified critical partition backups are under `backups/critical-baseline`. Re-enabling Android is a separate, explicitly approved operation. No destructive changes are authorized by this report.

## Files
- Test comparison: `reports/eightcore-postboot-20261110T1636/comparison.json`.
- Original kernel/ADT/menu rollback receipts and backups remain on PC and ESP.
- As of this report the tablet is in **TWRP** and the ESP block device has been verified read-only (`blockdev --getro /dev/block/sda29 = 1`).

## Evidence limits
Absence of USB re-enumeration is not evidence of a finished iPadOS boot. A launchd/SpringBoard process existing does not imply a usable graphics session or App Store capability. External posts about other nabu/iPadOS ports without published and qualified device-matched boot images are not flashable evidence.
