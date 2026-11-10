# Latest visible failure and USB recovery research - 2026-11-10

The owner reports the standard compositor repair still shows green/blue/magenta bars. The previously accepted reboot and installed hashes prove installation, not a visible iPadOS boot. At the first host check after this report neither ADB, Fastboot nor the known USB debug identity was reachable. Do not infer the failing stage or repeat the preceding kernel log as evidence for this build.

`scripts/capture_standard_compositor.py` waits for a bounded recovery/Fastboot connection, verifies nabu and the exact temporary recovery image, RAM-boots recovery once if necessary, mounts the ESP block-read-only, verifies current kernel/cache/menu hashes and retrieves one CRC-checked log. It never persistently flashes or automatically retries XNU. The user has been told the physical Fastboot step is necessary while the current kernel lacks a reachable control channel.

## Primary-source comparison

- https://github.com/zzweiqing/UniXNU-nabu : latest source is still our pinned `54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9`; no newer Pad 5 repair was found there.
- https://github.com/Lux12138/unixnu-nabu/blob/main/CURRENT-STATE.md : reports running Apple daemons without a functioning display provider; its board has expanded 12 GiB RAM. Do not copy its memory layout onto this 6 GiB unit.
- https://github.com/mytiantian001/iPadOS-nabu : explicitly describes an experimental iPadOS 16.6.1 port without a usable UI, with unfinished USB/touch. Its different Apple ABI and storage layout are not interchangeable with 21H16.
- https://github.com/iOSNJBrepo/macOS-uke : documents Pad 7 / SM7675 / Adreno 732, not Pad 5 / SM8150 / A640. Its cache-coherency and plugin-trust lessons are relevant concepts; the device binaries and addresses are not interchangeable.
- https://github.com/UniXNU/UniXNU : recent display/Metal and console changes were inspected. Many target macOS or 21H461 and need targeted ABI qualification before any 21H16 backport. Do not replace the entire pinned tree as a speculative fix.

## Alternative to repeated manual boot cycles

https://github.com/Lux12138/nabu-usb-cdc at `6c3930b746ab316fbf3bd86c1795a4338ab4f589` documents a board-tested CDC console, session/sequence/CRC control frames and a timed watchdog return to recovery. The reported control RX can stop after 70-90 seconds; the docs also describe intermittent TX stalls. An accepted reboot command alone is not successful recovery.

Its `docs/07-control-channel-and-wdt-park.md` describes a direct PSCI reset plus APSS watchdog and a prearranged recovery boot message. Its published module instructions instead preserve normal shutdown and private translated DMA. The SM8150 profile in this snapshot selects an inherited identity/bypass lease. These source/document differences, XNU 21H461/Darwin22 patch assumptions and the recovery-target layout must be resolved before integration. Do not run the supplied whole-device pipeline: it assumes the author's machine, storage and firmware.

Our existing nabu source already contains `usb/NabuUsbCaptureCdc.cpp`, compiled under captured builds, with explicit CDC init/SMMU gates. It is a bounded one-way log transport, not the above control/reboot implementation. Enabling it does not establish a working USB channel or automatic recovery.

The new explicit-dispatch `audit-nabu-usb-console.yml` runs the published USB controller/SM8150 host models and cross-compilation checks without Apple inputs or device access. This is the first qualification step, not a completed kernel port or hardware acceptance.

## Next decision

Read the current repair's new addon extraction/mount results, UI activation/thread samples, VSYNC counts and frame counters. Choose the next graphics change from that evidence. In parallel, qualify a reversible control/recovery path. Check the actual Android slot/partition state before claiming Android is erased or attempting any restoration; no Android reinstall or data wipe is authorized by this research note.
