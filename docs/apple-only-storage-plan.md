# Apple-only storage migration plan — Xiaomi Pad 5 6 GB / 128 GB

**Status:** offline layout feasibility validated against the **actual connected tablet** on 2026-11-06. The owner explicitly wants **real iPadOS as the only installed OS**, not Android dual boot. **No Apple OS or SystemOS bytes have yet been written to `userdata`.** Keep a device-recovery route while constructing the boot chain.

## Geometry confirmed using root ADB + `sgdisk`

Physical UFS LUN 0: 125,585,850,368 bytes, 30,660,608 × 4096-byte logical sectors. GPT has **32 partition entries** and no free space. The following are existing GPT entries, not proposed new partitions:

| Existing entry | LBA start–end (4 KiB logical) | Current size | Destination |
|---|---|---|---|
| #23 `super` | 49,152–2,277,375 | 8.5 GiB | Reclaimable Android system space *after* successful Apple boot, not required for initial XNU launch |
| #29 `cust` | 2,359,360–2,621,503 | 1 GiB | Existing UEFI FAT32 boot environment; currently first 256 MiB contains the verified boot-menu test |
| #30 `rescue` | 2,621,504–2,654,271 | 128 MiB | Keep until independent boot and recovery path proven |
| #31 `userdata` | 2,654,272–30,660,602 | 106.8 GiB | Planned Apple-only virtual-disk carrier, replacing *all* Android user data once qualified |

Existing bootloader, modem, firmware, UFS GPT and critical boot partitions on LUNs sda–sdf are **not expendable Android data**. Retain their identities and contents unless a board-specific boot/recovery test proves a modification safe.

## Proposed Apple-only windows *within* current #31 `userdata`

| Intended content | Physical LBA first–last | Allocated bytes | Meaning |
|---|---|---:|---|
| Reserved gap | 2,654,272–2,739,967 | 351,010,816 | Alignment/early staging |
| Apple OS 17.7 (21H16) | 2,739,968–4,204,808 | 5,999,988,736 | Original 5,999,986,176-byte raw OS virtual disk padded to 4 KiB |
| Apple SystemOS | 4,204,809–5,011,208 | 3,303,014,400 | Original SystemOS APFS image |
| Future Apple Data | 5,011,209–30,660,602 | 105,059,917,824 | 97.845 GiB **reserved but not implemented as persistent APFS Data** |

The pinned UniXNU-nabu source specifies `first_lba=2739968`, `last_lba=5011208`, `lba_bytes=4096`. These values are **currently inside encrypted Android `userdata`**. They are **unsafe while Android data remains**; the owner authorizes its eventual destruction, but approval alone does not make the current kernel capable of reading these images.

A GPT repartition is not necessary for initial source-port window reads: the existing #31 entry can act as the carrier after a deliberate data wipe. The source storage driver uses explicit LBA windows, not independent GPT entries. Any future conventional repartition must account for 32-entry GPT capacity, backup CRCs and UFS logical-sector geometry.

## Prerequisite gates before the irreversible OS install

1. Pass XNU **read-only UFS driver** host compilation and validate output identity.
2. Compile a full nabu owner-root kernel (not the earlier bootstrap prelink) with owner public-key trust anchor compatible with **locally generated owner policies**. Keep private key on owner PC.
3. Stage actual nabu Apple-style device tree, trust caches, Data seed, logging, kernel and DarwinBoot on ESP. Boot on the real Pad 5 and establish a reproducible recovery path.
4. Demonstrate XNU can read storage **without writing** or panicking, and record persistent boot evidence.
5. Only then deliberately erase the Android `userdata` contents and install original Apple OS + SystemOS windows with read-after-write hashes and a tested rollback. The owner does not want Android preserved, but critical Qualcomm boot partitions must remain.
6. Implement or validate APFS Data persistence and boot into iPadOS userland. The current 32 MiB RAM-only APFS test is not a persistent user-data implementation.

## Proven steps and evidence

- The real Pad 5 displayed the UniXNU v0.1.0 menu from `cust` with owner-supplied photo.
- Real-device `cust` FAT32 first 256 MiB was verified read-after-write; 1 GiB pre-UEFI `cust` backed up twice under SHA-256.
- Bootloader `fastboot boot` accepted the temporary UEFI image; unrelated Android data/boot GPT was not flashed.
- Private GitHub source builds successfully compiled a bootstrap candidate, EFI loaders, and an ARM64 QEMU handoff. **Those results do not validate full iPadOS boot.**
- Read-only geometry script: `Desktop\NABU_IPADOS_LAB\PLAN_IPADOS_ONLY_STORAGE.py`; report `build-artifacts\apple-only-storage-plan.json`.

**Status claims:** storage geometry `PASS`; Apple-only data conversion `NOT PERFORMED`; full XNU hardware boot `NOT PROVEN`; persistent iPadOS `NOT INSTALLED`.

## 6 November 2026 — UFS read-only build gate completed

GitHub Actions [run 42280031790](https://github.com/giacomomilanesi/nabu-ipados-macos-build/actions/runs/42280031790) built the `nabu_ufs_readonly_defconfig` host candidate and uploaded `nabu-ufs-readonly-kernel-unqualified` (artifact 13535717037). The prelinked kernel digest logged by the build is `b6b01d0f186a59136b87a8ae92d94dbbcbcdd17cae4eec8cda0e78b690ea4265`.

The complete private evidence archive (13535986435) was independently SHA-256 verified and extracted on the owner's PC. Its **final** `xnu-logs/kernel.log` (12,429,995 bytes) ends with `built kernel at .../mach.development.bcm2837` and contains no linker errors. The separate `kernel-bootstrap.log` includes an expected early unresolved-symbol link because the framework first compiles before platform archives are produced. The preliminary failure must not be interpreted as the final build result.

The new `build-nabu-ufs-owner-root.yml` workflow uses owner-generated OS/SystemOS signed hash manifests and public trust-anchor bytes downloaded from a private repository release, with the exact archive hashes checked and the owner's private signing key never uploaded. It also mandates a rebased second static trust-cache patch. **That full owner-root workflow has been prepared and YAML-checked but not yet confirmed running or passing.**

There is still **no demonstrated physical XNU root mount and no installed Apple OS** on this tablet. Do not overwrite the current Android `userdata` until a full owner-root candidate and read-only physical storage probe work.
