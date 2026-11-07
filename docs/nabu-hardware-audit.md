# Hardware audit — owner's Xiaomi Pad 5 (nabu), retail 6 GB

This describes the **connected, real hardware**, not assumptions from other developers' custom-partitioned tablets. All observations were made with ADB/Fastboot read-only commands after a temporary TWRP recovery boot.

## Boot
- Fastboot device: `nabu`, USB Fastboot `18D1:D00D`
- `getvar:unlocked`: **yes**
- `getvar:secure`: **yes**
- Current slot: `b`; two slots
- A temporary TWRP boot succeeded with Fastboot `download` / `boot`, no flash
- Official `fastboot.exe` did not recognize the WinUSB-bound interface, but a read-only PyUSB Fastboot client did

## RAM (real device tree)
`/proc/device-tree/memory/reg`: two 32-bit address/size cells, three banks:

| Base | Length | Region (inclusive) |
|---|---:|---|
| `0x80000000` | `0x3CC00000` | `0x80000000..0xBCBFFFFF` |
| `0xC0000000` | `0x80000000` | `0xC0000000..0x13FFFFFFF` |
| `0x140000000` | `0xC0000000` | `0x140000000..0x1FFFFFFFF` |

Total enumerated memory is approximately **5.949 GiB**. Not all of it is available to the kernel because of reserved areas. Any UniXNU physical memory or framebuffer handoff must be checked against these banks, not guessed from the marketing RAM figure.

## Storage
- UFS logical unit `sda` uses **4096-byte sectors**.
- Actual `userdata` GPT partition is `/dev/block/sda31`, sector range **2654272–30660602**, approximately 106.8 GiB.
- Actual `cust` GPT partition is `/dev/block/sda29`, approximately 1 GiB. It is **not yet an EFI partition**.
- There is no `/dev/block/by-name/esp` or `linux` partition in the original layout.
- The GPT has no free sectors for a new unallocated OS partition.
- **Critical overlap:** the published `zzweiqing/UniXNU-nabu` `board.toml` data windows use sectors **2739968–5011208**, which are **inside this tablet's Android userdata**. Do not apply these offsets as a safe unallocated region.
- The source port assumes an existing UEFI/rEFInd + FAT ESP boot environment that is absent on this device.

## Firmware
- Original Apple iPadOS 17.7 (21H16) IPSW obtained directly from Apple on the owner's PC.
- Apple OS and SystemOS APFS UUIDs match the source port's pinned UUIDs.
- Owner-generated RSA verified-root manifests are **not Apple signatures** and remain on the PC only.
- Full source-based XNU kernel and any iPadOS boot success remain **unverified**.

## Recovery copies
- GPT backups for six UFS logical units and 22 critical partition images were captured to the PC and copied to an external F: drive.
- The Android `cust`, `super`, and `metadata` partition backups are separate, ongoing tasks.
- No userdata or full personal-data backup has been claimed.

## Guardrails
No `flash`, `erase`, GPT rewrite, or storage repartitioning until a built kernel candidate and an independent, tested recovery path exist. A `fastboot boot` test remains preferable to replacing `boot_a` or `boot_b`. This private repository may contain source/build metadata only; do **not** commit Apple IPSW/DMG files, local owner private keys, or device backups.

## November 6, 2026 — verified offline EFI and temporary physical UEFI test

- Successful GitHub run **42263766563**: UniXNU ARM64 UEFI application and DarwinBoot driver compiled; QEMU test reached the UniXNU menu and HelloPayload checks passed.
- Successful GitHub run **42264760457**: using pinned EFI binaries and the experimental 50.6 MB ARM64 kernel candidate, QEMU serial logs showed `DARWINBOOT: loader v2 installed EL1` and `DARWINBOOT: inputs validated; exiting boot services`. That is an **emulated** UEFI handoff, not proof XNU or iPadOS boots on the Pad 5.
- The kernel candidate passed static checks against the actual DarwinBoot parser, including exactly one ARM64 `LC_UNIXTHREAD` and a bounded executable entry. A separate older document incorrectly described `LC_MAIN`.
- On the physical Pad 5, release image `MiPad5.UEFI-v2608.03_nSB.img` (SHA-256 `f4d4ba5574efeb625b55a0bca0d3eeeaf030bf5c8c42caeaf2c7c260f858ba2c`) was transferred by direct USB Fastboot to RAM and the bootloader replied `OKAY` for both the download and the `boot` command. USB Fastboot then disconnected. **No tablet display confirmation or iPadOS execution confirmation is yet available.**
- No `flash`, `erase`, `set_active`, GPT rewrite or write to `userdata` was issued in the physical test. The test UEFI image has a five-byte ramdisk and there is still no EFI System Partition; it cannot load iPadOS from storage as-is.
- Windows F: backup comparison covered **22 critical partition images and six UFS GPT backup files**; all matched the source files by SHA-256.

**Next physical milestone:** user-supplied visual confirmation of what the UEFI image displays and a return to Android/recovery; device-specific temporary UEFI + ESP staging must be demonstrated before any Android wipe.

## Physical EFI menu confirmed — 6 November 2026

The owner supplied a photograph from the real Xiaomi Pad 5 screen showing the `Pad 5 - UEFI Hardware Check` menu, UniXNU **version 0.1.0**, config `\\EFI\\UniXNU\\unixnu.toml`, and three menu entries: `Test UEFI (no Android changes)`, `Restart tablet`, and `Power off tablet`. The default test entry had a **169-second** countdown at the time of the photograph. Status showed `drivers 0 loaded / 0 failed`, `kits 0`, `acpi 0`.

This confirms that the physical tablet executed UEFI, discovered the FAT32 image written into the existing `cust` partition and started the UniXNU menu. It supersedes the previous failed temporary UEFI test (which had returned to Android because the ESP environment had not existed). The owner has not yet confirmed the HelloPayload self-test result after the countdown. **XNU, Apple iPadOS, SpringBoard, touchscreen and storage mounting remain untested.** Never represent this as iPadOS installation.

Physical installation scope: exactly 256 MiB at the beginning of `/dev/block/sda29` (`cust`), SHA256 `de28c409b583c359f8413ea7d00b15bfa229a3e0550b4c45c8af7cb13ca80a26`, after matching two complete 1 GiB `cust` backups with SHA256 `66f7e2ed02506ff9e619e965e33928b919f0faf48e3ebadc4212d1bf8ad4bcce`. No GPT rewrite or Android `userdata`/boot partition modification.

Next gate: owner confirmation that the harmless HelloPayload executes successfully or reports a specific screen error, followed by a *separate*, explicitly instrumented physical DarwinBoot/XNU payload with actual nabu device-tree sidecar and a preserved recovery path.

## TWRP cust mount diagnostic after physical UEFI — 6 Nov 2026

After the owner physically booted the UniXNU menu from the 256MiB FAT32 ESP staged in the start of the original `cust` partition, they reported that ArKT V-4 TWRP prompted for the Android data password and failed mounting `cust`.

Read-only recovery inspection via root ADB on the actual nabu (`33288984`) confirms:
- `/tmp/recovery.log` contains repeated `Failed to mount '/cust' (I/O error)`.
- `/dev/block/by-name/cust` resolves to `/dev/block/sda29`; the first sector now has a FAT32 BPB and `FAT32` signature (matching the UEFI test image), so recovery's original Android cust mount expectation no longer matches.
- `/cust` is not mounted. `/data` is mounted as F2FS via `/dev/block/dm-5`; `/metadata` is mounted separately, confirming data decryption/mount worked.
- TWRP also logged `Unable to mount '/esp'` and `Unable to mount '/linux'`, partitions absent from the real retail GPT.
- The physical UniXNU menu photograph confirms that the UEFI firmware previously discovered and read files on the repurposed `cust` FAT32 image.
- An I/O-error string alone cannot rule out other storage problems; do not treat it as proof of flash damage or try automatic filesystem repair.
- The complete pre-ESP `cust` contents were backed up in two verified 1GiB copies before modification; Android's original `cust` functionality may be unavailable until restoration.

**Operational rule:** avoid mounting or repairing `cust` as Android ext4 while it contains the FAT32 ESP. Never format or wipe `/data` in response to this error. No Android data password was collected or recorded. Physical UEFI boot success is not iPadOS boot success.

## Native-4KiB FAT32 fix and owner-root first-stage packaging — 6 November 2026

Read-only physical TWRP Linux kernel logs proved the earlier `/cust` mount failure is **not a generic I/O failure**: `FAT-fs (sda29): logical sector size too small for device (logical sector size = 512)`. Both the tablet's UFS logical and physical sector sizes are **4096 bytes**. The first 256MiB EFI image was authored with 512-byte FAT logical sectors and succeeded in the UEFI boot manager but failed to mount on TWRP Linux.

A new **512MiB FAT32 host image** was built with **4096-byte FAT sectors**, preserving the UniXNU EFI manager and HelloPayload and additionally placing the independently built **123,490,304-byte owner-root XNU Mach-O** plus a 10,388-byte Pad 5-specific Apple device-tree sidecar under `EFI/UniXNU/Payloads`. Its boot menu names the default `XNU early boot (NO INSTALL)` and explicitly sets `native-ufs-root=0`; it contains no iPadOS OS or SystemOS image and cannot write Android userdata.

- Native-sector image SHA-256: `22e65578990a5f2170c42448871e3dcb7382412492485cef20323ae6fa34c631`.
- The tablet's own `fsck.fat -n -v` reported a **clean filesystem**, 4096 bytes/sector, 4096 bytes/cluster, 129,006 data clusters, 13 files, exit code 0. The recovery mounted the **RAM copy** read-only using a Linux loop device successfully.
- Original source ADT generator `make-sheng-adt.py` is not present in the pinned UniXNU checkout. The first-stage ADT was generated locally using actual physical memory/GIC/UFS registers checked against the owner tablet's private FDT. The original 13-point legacy validator passes 13 checks and rejects only 256-byte random-seed length (it expects 64; newer XNU generator requires 256). **This discrepancy remains unqualified for hardware XNU execution.**
- The private raw firmware FDT and locally generated stable chip identity are **not committed or uploaded**.
- The 4KiB-sector image is an **early boot diagnostic** only, not an iPadOS installer. Before any physical write, keep the working first-generation EFI image and full 1GiB `cust` backup recoverable and verify exact device and block geometry.

**Never infer success of iPadOS mounting from a clean FAT/UEFI boot.** A real Pad 5 physical XNU handoff, trusted Apple root mount, and supported persistent Data path still need verification.

## Physical owner-root kernel early-boot trial — 6 November 2026

The owner explicitly authorized progressing toward an Apple-only Pad 5. A **non-installing** XNU entry was prepared, because a successful host Xcode build does **not** establish on-device kernel boot or the ability to mount Apple's OS volumes.

Completed on the real tablet:

1. Verified original, working `cust` FAT32 256MiB prefix SHA-256 `de28c409b583c359f8413ea7d00b15bfa229a3e0550b4c45c8af7cb13ca80a26`.
2. Backed up the entire current **1GiB** `cust` (containing the first photographed working UniXNU menu) to both the PC and external F: and checked both against device SHA-256 `d5f72fd1e73c2b24f0c300807f9129da7077cd63dc6d1ac6049fe4402584eb77`. These are independent of the original pre-UEFI `cust` backups.
3. Generated a new **512MiB FAT32 ESP with 4,096-byte logical sectors** and stored `UniXNU.efi`, `DarwinBoot.efi`, `HelloPayload.efi`, the verified **123,490,304-byte** `nabu_ufs_root_defconfig` XNU `kernel.macho`, and its hardware-diagnostic `kernel.macho.adt` sidecar. Image SHA-256: `22e65578990a5f2170c42448871e3dcb7382412492485cef20323ae6fa34c631`.
4. The tablet's **own** `fsck.fat -n -v` (read-only) passed with 4KiB sectors and 13 files; a read-only Linux loop mount of the RAM-copied image passed.
5. Wrote **exactly 512MiB** to the start of `/dev/block/sda29` only, after verifying backups, nabu device identity, battery level, staging checksum, original current `cust` whole-partition checksum, current FAT prefix, and unmounted state. Direct device readback SHA-256 equals the new image hash.
6. TWRP mounted the new actual `cust` FAT32 partition read-only **successfully**, confirming the earlier TWRP 512B-vs-4096B mount failure is fixed.
7. Returned temporarily to Fastboot; `fastboot boot` accepted the same released Xiaomi Pad 5 UEFI image via USB (image transfer verified, response `OKAY`). **No display evidence of this new XNU boot attempt has yet been obtained.**

The modified UEFI menu default is `xnu-first` at 25 seconds, explicitly titled `XNU early boot (NO INSTALL)`, with args `-v serial=3 debug=0x14e kt_fixed_zones=120 cpus=1 native-ufs-root=0`. It does **not** write any Apple OS/SystemOS images, format userdata, change the GPT, or enable native UFS root mounting. It retains the UEFI HelloPayload self-test and reset/shutdown entries.

**Important limitations:** The platform's pinned `make-sheng-adt.py` generator is missing. A first-stage ADT was generated from the real private nabu FDT with verified DRAM/GIC/UFS addresses. Thirteen of fourteen legacy ADT checks passed; the older validator requires a 64-byte random seed, while the newer XNU source generator needs 256 bytes. Therefore this ADT is an experimental early boot diagnostic, **not a complete hardware UFS resource description or a production-qualified kernel boot**. The private raw firmware device tree and chip identity remain on the owner's PC only.

**Rollback:** full 1GiB known-working `cust` backup SHA `d5f72fd1e73c2b24f0c300807f9129da7077cd63dc6d1ac6049fe4402584eb77` on C: and F:. The Android `userdata`, `boot`, `super` and GPT remain unmodified by this test.

**Installation status:** NOT installed; requires actual successful XNU hardware startup, corrected UFS provider ADT, successful Apple OS/SystemOS read/mount and Data persistence before safe destructive Apple-only migration.
