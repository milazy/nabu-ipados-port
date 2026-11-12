# Batch 7 hardware investigation

This is an experimental backlight trial and an investigation of Wi-Fi DMA and
Settings. It is not a daily-usable iPadOS release. Apple and device firmware,
EFS dumps, complete boot logs, MAC addresses and network credentials stay on
the owner's PC. No boot partition or persistent firmware writes are involved.

## Baseline captured on 2026-11-12

Project source: `271f443c400a434c8624c0a6028aaf00b8b5e48d`.
Kernel workflow: `43243118463`; userland workflow: `43243117405`.
UniXNU: `245aca1a9ec5b730b1cad80fade295800d2981f1`.
Nabu layer: `54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9`.
Apple input: iPadOS 17.7, 21H16, iPad7,11.

Read-only ADB recovery collection used `adb -s OWNER_SERIAL pull
/tmp/XNU2LOG.BIN ...`, `pull /sys/firmware/fdt ...`, and device-tree properties
under `/sys/firmware/devicetree/base`. The serial is intentionally omitted.
The ESP was read-only (`blockdev --getro /dev/block/sda29` returned 1).
Baseline payload files were pulled from a FAT read-only mount and hashed on
the host; the kernel and ADT hashes also matched the device-side hashes.

| Input | SHA-256 |
|---|---|
| Boot log container | `a931b465705c6aab8449cbd96dddb252861e89ee704a29c67b4e7e0a1523adb0` |
| Live device tree | `7a11e9fa8413c7f6da22811e64e26389887060a5021291e2749226be8bbaf389` |
| Kernel | `3e0a5cc047df13965df204734beb095908387993c7533a95eaffed58a8291c67` |
| ADT | `ad6b53b7131900b4764dd6649d6ace425374cc3c06f4fb18cd67f6474fa4e772` |
| Addon | `12d95f3b04f41c13b90cb159c4d9927810f13f9ecb1d73bae392cb5dad1dd0ce` |
| Trust cache | `b55268b55cbbe6e37411d20785c4838ded2a5c55c3e56ac2e227addce851daf6` |
| Menu | `cd660c22cfd0a9185dfd03cc0af75758f878ad28ed09188468e80033aa17b349` |
| RAM UEFI image | `f4d4ba5574efeb625b55a0bca0d3eeeaf030bf5c8c42caeaf2c7c260f858ba2c` |

`nabu_log_volume.decode_container` selected CRC-valid sequence 4531:
742614 payload bytes, SHA-256
`39d4a9182da0f26d92c6147639ce4ed702cc4a09b2b6d5ce85998afc8d6cc193`.
The decoder reports 220 lost bytes. This is a valid committed snapshot, not a
guarantee of complete logging or of events after its final commit. Do not
concatenate both NABULOG2 slots: that duplicates older snapshots.

## Wi-Fi: firmware boots; DMA remains unimplemented

Actual log progression:

```
boot: auth and reset -> 0/0
smp2p: modem state 6 ready handover
boot: modem ready after 100 ms
glink: IPCRTR open (rcid 2)
wlfw: server at 0:23
wlfw: < MSA READY
wlfw: < FW READY
wlfw: wlan config sent, mission mode on
[ 5335] radio: ce: the WLAN SMMU stream is not set up: no DMA, not starting
```

The refreshed DT confirms MPSS `0x8e000000 + 0x09600000`, WLAN MSA
`0x8bc00000 + 0x180000`, SMEM `0x86000000 + 0x200000`, WLAN SID `0x640`
mask `1`, and IOVA `0xa0000000 + 0x10000000`. Linux recovery exposes icnss
in IOMMU group 6. Group membership does not establish a usable XNU mapping.

The donor uses a fixed physical DMA pool at `0xe0000000 + 0x01000000` and
sets `smmu_done` only after programming an identity context. Batch 6 skips
that programming, so the refusal is expected. Removing the refusal would
not prove DMA safety. Before enabling copy engines, establish a reserved
pool excluded from XNU and an actual WLAN mapping, then prove CE completion.
The apps SMMU must never be probed from XNU.

Additional source evidence: Mu-Silicium revision
`46e4ac0800862fb3ee6da09f0028fbef4e767648` selects HanaPkg for nabu;
Hana `PlatformInitialize` calls `ArmSmmuDetach` preserving only display SIDs.
This revision has not been matched to the owner's RAM UEFI binary. It is
evidence against assuming inherited WLAN DMA, not proof of that binary's
register state. A candidate solution is a WLAN-only UEFI mapping/handoff
before ExitBootServices with a kernel-validated reserved pool. It must not
change UFS/display streams, and requires a separate opt-in boot path and
device validation before CE is enabled.

## Brightness: observed failure and gated correction

The live DT confirms `i2c@880000`, `ktz8866@11`, `qcom,i2c-geni`, GCC clock
IDs `0x51/0x79/0x7a`, and enabled status. Linux recovery reports maximum
brightness 2047 and current brightness 870 (read-only sysfs observations).

Batch 6 logged slave AHB CBCR `0x80000002`, called it OFF, and stopped.
Linux `drivers/clk/qcom/gcc-sm8150.c` places the SE0 CBCR at `0x17144`,
whereas batch 6 used `0x17030`. The slave AHB CBCR has hardware clock gating
at bit 1; `clk-branch.c:clk_branch_wait` skips halt polling in that mode.

`nabu-backlight-v2=1` selects corrected offset and HWCG interpretation,
requires all enable votes, exits on failed MMIO or I2C errors, and preserves
brightness if its BKS source is absent. The original mode remains available.
An I2C acknowledgement alone will not establish slider operation: require
the marker, successful writes and observed dimming with the actual UI slider.

## Settings

Preferences PID 319 main thread TID 4152 has the same 21-frame wait in
samples 22 through 27. The log reports a subsequent `0x8BADF00D` termination
and failure to terminate gracefully after five seconds. That termination
message alone does not identify the original blocking service.
`symbolize/request.txt` contains only the shared-cache addresses and the
captured slide `0x1a798000`, for symbolication against the exact 21H16 cache.

Run `43251838284` successfully symbolized the main thread:
`kevent_id -> dispatch wait for queue -> dispatch_sync_f_slow ->
PKIconImageCache imageForKey: -> pk_updateSpecifiers:withIconsFromCache: ->
PSUIPrefsListController specifiers`. Its final optional string-search step
failed because the search file contained only comments; the symbolication
artifact is valid. The workflow now handles a comment-only file without
turning a successful symbolication into a failure.

Iconservicesagent repeatedly crashes at PC zero, LR `0x1b1e86ac4`, slide
`0x1a798000`: unslid LR `0x1976eeac4`. Prior exact-21H16 symbolication
`43118114216` identifies this as `CI::GLContext::init + 220` immediately
after a null indirect call. The installed cache points at the signed
`/usr/bin/iconservicesagent` and the addon contains `NabuIconFix.dylib`.
This establishes that GL is still reached for some requests; it does not
prove which initializer bypasses the shim. Further worker symbolication is
requested in run `43253208976`.

## Candidate build and current qualification

Userland source `7fda7f73fe5c939c845ee9623ea6dac69cda3a44`, successful
macOS/Xcode workflow `43251838244`. Installer/evidence source
`dc343df8f99193a6353d71e497fb0fecf8e94cee`.

| Candidate item | SHA-256 |
|---|---|
| Signed backlight daemon | `2fb96b8c5934833d489940728f10e16c8565fc6c6b73acdb61faa7f417a09d44` |
| Candidate addon | `4a528ce9c72ee5dc2656a059df6bc1ba4bf7ded190488ab748716d66ea5a2df1` |
| Candidate trust cache | `9ff833b2db4fa4452d344f56dc1059ee6c3186cb76d5dd09e33fdab6a2661e52` |
| Candidate menu | `7a922d6aff13dc18df1ebfc3c1f74e2d0c5a53d4b03b517254f75a38d5ef3d9e` |

The candidate kernel and ADT hashes equal the baseline. Host assembly
verified all 98 non-backlight addon members unchanged and added one new
CodeDirectory hash. Menu isolation checks, Python compilation, shell syntax
checks and diff whitespace checks passed. They do not constitute hardware
qualification.

| Function | Compiled | Attached on device | End-to-end verified |
|---|---|---|---|
| Backlight v2 | Yes, run 43251838244 | No | No |
| Wi-Fi modem/GLINK/WLFW | Yes, baseline | Yes, CRC-valid batch-6 log | Firmware mission mode only |
| Wi-Fi scan/join/IP/SSH | Donor pieces only | Radio refused DMA start | No |
| Home-screen icons | Baseline shim | Present; daemon still crashes | Owner-reported home-screen artwork only |
| Settings | Baseline OS | Main thread stuck in icon cache | No, watchdog termination |
| IPA installer | Yes, baseline | Ran, seen=0 installed=0 | No IPA tested |

ESP installation was rejected by automatic approval review before the
command reached the PC; explicit owner confirmation is pending. The tablet
remains in recovery with its ESP read-only. This candidate has not booted,
and no hardware-qualified release is claimed.

## Trial installation and rollback

`tools/pc/prepare_batch7.py` validates all five baseline hashes, replaces
only `bin/nabu-backlight` in the addon, verifies every other member byte for
byte, and appends its ad-hoc CodeDirectory hash to the existing trust cache.
The existing kernel and ADT are copied unchanged to a new candidate basename.

The generated installer checks recovery device identity, battery, ESP size,
all baseline/staging hashes, destination absence and free space. It keeps
`unixnu.toml.pre-batch7`, writes new candidate files, remounts read-only and
verifies SHA-256 before activating the menu. It then verifies the menu and
all original payloads. Error cleanup attempts to unmount and mark the ESP
read-only. New candidate files have no overwritten predecessor; the original
payload set remains in place. It never erases files or invokes fastboot.

The menu preserves every original entry and adds independent backlight-v2,
backlight-off and AppSync opt-in entries. Roll back by selecting the original
`xnu-existing-ui-policy` entry. If the menu itself must be restored, RAM-boot
the pinned TWRP image, back up the current menu under a new suffix, restore
`unixnu.toml.pre-batch7`, and verify its baseline SHA-256 by read-back. Never
flash recovery, UEFI or a boot partition.
