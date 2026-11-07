# Pivot: authentic iPadOS 17.7 on Xiaomi Pad 5 — source-led integration

Status date: 2026-11-07. **Host-side development only. No tablet operations or installation authorized by this document.**

## Decision

Stop repetitive colored-bar and reset-only XNU probes as the default path. Prioritize a source-built, board-specific, authentic iPadOS 17.7 (21H16) candidate using the most advanced available `nabu` port. Preserve the existing experimental ESP, two 1 GiB `cust` backups, stock Android, and all prior diagnostic evidence. Do not treat an XNU entry or UEFI menu as an Apple OS boot.

## Source evidence reviewed

- `zzweiqing/UniXNU-nabu` at published `54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9` reports eight-core XNU, UFS root (OS + SystemOS), NT36523 touch, A640 GPU composition, and interactive SpringBoard with a reported scanout stall. Persistent Data, networking, audio, power management are **not yet implemented** according to its README and porting record. These are maintainer claims, not reproduced on this owner's tablet.
- `Lux12138/unixnu-nabu` reports a different bring-up path reaching `load_init_program()` then failing to find `/sbin/launchd`; it is not evidence of a complete install.
- `Scion-Project/hakios-starlte` is catalogued as a Galaxy S9 Exynos 9810 running iOS 16.5 via HakiOS. It demonstrates feasibility on some Android hardware, but neither its ARM platform code nor board drivers are drop-in compatible with Snapdragon 860/SM8150 nabu.
- The user's local `C:\Users\Giacomo\Desktop\NABU_IPADOS_LAB\UniXNU-nabu` is already a clone of `zzweiqing/UniXNU-nabu` at `54b4f98`. **Numerous tracked local modifications were observed; do not reset, clean, pull over, or overwrite this tree**. Use a separate detached worktree/copy for any integration.

## Owner Pad 5 versus maintainer assumptions

| Contract | Current owner experiment | Advanced source port | Integration rule |
|---|---|---|---|
| Kernel boot | Owner-root XNU with entry/MMU/_arm_init diagnostics; no proven continuous normal XNU boot | Reports actual iPadOS 17.7 launchd/SpringBoard path | Inspect and reproduce exact versioned source/patches, never infer success from bars |
| Root | Current menu explicitly `native-ufs-root=0`; no Apple OS/SystemOS volumes in the diagnostic image | `native-ufs-root=1`, UFS OS/SystemOS windows, prelinked drivers/trust cache | Build owner-specific root configuration on PC before any on-device image staging |
| Storage | Physical `cust` 1 GiB at `/dev/block/sda29`, Android `userdata` intact, 128 GiB UFS with 4096 B sectors | Maintainer's `board.toml` uses fixed UFS LBA ranges for **their** available storage and a 334 MiB ESP | Never copy fixed LBAs/partitions or repurpose userdata; validate owner GPT and only choose non-overlapping space after explicit review |
| RAM/firmware | Owner hardware DRAM map must be reconstructed and verified; UEFI booted to RAM via Fastboot | Different maintainer layout/firmware/rEFInd assumptions; ADT contains RAM windows | Do not reuse fixed DRAM / reserved framebuffer addresses or firmware assumptions without physical correspondence |
| Apple services | Authentic user-owned 21H16 IPSW available | Reported interactive Apple UI | App Store, account services, signing/activation remain unverified; don't promise them |

## Host-only work sequence

1. Preserve the modified `UniXNU-nabu` tree and prior rollback receipts. Build in a separate clean worktree at an explicit source revision.
2. Audit `board.toml`, `dts/nabu.dts`, `configs/nabu_ufs_gpu_metal_defconfig`, `source-ci/prepare_source.py`, `patches/xnu/`, `scripts/package.sh`, and `docs/BUILD-INPUTS.zh-CN.md`; record exact upstream and component commit pins.
3. Generate the IPSW small-input package locally from the owner's existing 21H16 IPSW, checking all expected member hashes. Never commit Apple binaries, proprietary blobs, personal keys, or device identifiers.
4. Reconcile real owner's memory map/ADT, actual GPT LBA geometry and UFS capabilities with source expectations; eliminate any reliance on the maintainer's free-space or 12-GiB-modified-device assumptions. Read-only source/host evidence first.
5. Compile a source-built full nabu XNU candidate and package a standalone host-only ESP candidate with proper prelink, UFS/root drivers and verified Apple volumes. Fail closed if any required input or integrity check is missing.
6. Independently inspect artifacts, recovery plan, and safety checks before **separately requesting a meaningful physical boot test**. No automatic tablet wiping, flashing, GPT editing, or Android erasure. Device-side installation may only be considered after a true successful UI/root boot and explicit approval.

## Boundary

The previous arm-init probe's return to Android does not prove genuine iPadOS functionality. The 512MiB `cust` experiment is not an installer. Preserve Android until a tested, bootable alternate system genuinely exists.
