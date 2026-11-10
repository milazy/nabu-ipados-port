# Combined Metal 8-core nabu candidate — installation record (10 Nov 2026)

This is a **boot-unverified experimental candidate**, not a working iPadOS release.

## Proven host-side
- GitHub Actions run `42849739317`, head `d294ad1477193eed489085731402ed8a6d7f337c`: compiled, signed and artifact uploaded.
- New Metal frontend combines async-creation API fixes and removal of completion-handler group waits in `waitUntilCompleted` and `waitUntilScheduled`.
- Exact wait-method transformations and 20 bounded async host cases were checked; **no real GPU render test was run by CI**.
- Addon and trustcache pass signed CodeDirectory/page-digest and paired-trust checks.

## Installed in recovery
- New addon SHA-256: `df3ada891f3a69c340b78db71a903fd2f681443e89884cce499143090a1f2db4`.
- New trustcache SHA-256: `a8c8ec8fd80217a763c0f40311fe84f66a9ffaf4cbc03146e01be8831e6fa3f6`.
- Unchanged kernel SHA-256: `7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d`.
- Unchanged eight-core ADT SHA-256: `429d9e7f39da10fb373b4a05081b9817843fe6c8e86e10728ac8fb74f7fbb514`.
- Unchanged menu SHA-256: `a7c022ab15e885546e860bd7612bcf623ad3c37adc6d90d5cf5100384f02bdd7`.
- Previous GPU addon and trustcache SHA-256: `6063ea23e49233479338d756c25e127d52c40da786018b4ed5212112dfc6c7d7` and `985f504f98ac96b69f04025934363b8e65da4fdc7236e0bc7cb3e87edf8a8457`.
- Tablet ESP backups: `/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho.gpuaddon.pre-combined-20261110` and `kernel-fulltrace-panic.macho.trustcache.pre-combined-20261110`.
- Local preparation and installer receipt: `build-artifacts/nabu-metal-combined-20261110/`.
- ESP readback succeeded and the block device was restored to **read-only**. Android partitions and iPadOS user data were not modified.

## Boot attempt
- UEFI RAM boot transferred 2,467,840 bytes with `FASTBOOT_IMAGE_TRANSFER_VERIFIED`, fastboot `boot` returned `OKAY`.
- This only confirms handoff. It does **not** demonstrate SpringBoard graphics, App Store support, or completed display frames.
- Prior boot log (before the combined fix) verified all eight cores and SpringBoard/backboardd alive, but `swaps accepted=0`, `scanout offered=0 done=0`.
- Screen outcome of this combined attempt remains to be observed before claiming any success.

## Further testing
Do not blindly flash further variants. Ask for the visible screen result and, if still stale, obtain a fresh CRC-verified `/esp/XNU2LOG.BIN` via temporary recovery for before/after submitted/completed GPU and scanout counters. Retain old signed addon and trustcache for byte-for-byte rollback.
