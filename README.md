# nabu iPadOS / UniXNU — private macOS build lab

This private repository runs an experimental **XNU bootstrap compilation** for the **Xiaomi Pad 5 (nabu)** using the published UniXNU sources and iPadOS 17.7 (21H16) inputs.

**Scope:** produce a *non-boot-qualified* kernel candidate and build logs. It is **not** an iPadOS ROM installer. Neither this repository nor its GitHub Actions workflow flashes partitions or connects to a device.

## Proven local device status (6 GB model)
- Bootloader reported unlocked using read-only Fastboot getvar commands
- Temporary TWRP recovery booted successfully via USB Fastboot RAM boot
- Tablet had its original Android GPT layout; `sda31` is `userdata`, **not an EFI partition**
- The original Apple IPSW was obtained and its kernelcache, DeviceTree, trust caches and original OS/SystemOS UUIDs validated
- GPT and critical partition backups are stored on the owner's PC and external F: drive, **not in GitHub**

## Workflow
Run **Actions → Build nabu XNU bootstrap (macOS) → Run workflow**.
It builds only `nabu_bootstrap_defconfig` using a pinned UniXNU source revision:
`245aca1a9ec5b730b1cad80fade295800d2981f1`.

It downloads only required Apple IPSW components directly from Apple's CDN, verifies their embedded SHA-256 pins, and keeps them off Git history. Outputs have 7-day private artifact retention. The original Apple material must never be redistributed publicly.

## Remaining obstacles
1. A working Apple/iOS SDK-compatible source build and a proper kernel + drivers assembly
2. A verified nabu-compatible UEFI + DarwinBoot handoff
3. Device-specific GPT/storage layout (the maintainer's ESP assumptions **must not** be used unmodified)
4. Genuine APFS root and SystemOS mount plus Data-volume bootstrap
5. Temporary boot tests and validated recovery **before** any partition erase

Private owner signing material is intentionally excluded. Signing a verified-root manifest with a local owner key is not equivalent to Apple-signed iPadOS.
