# Frontend check fix: why the combined candidate showed no frames (11 Nov 2026)

Hardware-UNVERIFIED until the owner reports the screen and a new log is read back.

## Host rebuilt after the Windows reinstall
- `scripts/SETUP_WINDOWS_HOST_20261111.ps1`: Git, Python 3.12, GitHub CLI, platform-tools, Google USB driver, repos.
- Fastboot on this unit enumerates as `18D1:D00D`, which `android_winusb.inf` does not list (Device Manager code 28).
  `NABU_IPADOS_LAB\bind_android_usb.ps1` binds the signed Google INF's "Android Bootloader Interface" to it
  (same as Device Manager > Have Disk). TWRP enumerates as `18D1:D001` and binds automatically.
- Tablet: `nabu`, unlocked, slot b, serial 33288984, TWRP MemTotal 5594820 kB, ESP = `sda29` (1 GiB, 98 % full, 22.6 MB free).
- External backup F: report says `verification_result: FAIL` and the completion marker is missing. Recheck before any destructive step.

## Readback of the combined candidate (read-only)
ESP mounted `ro` after `blockdev --setro`. All five installed hashes matched `COMBINED_METAL_20261110_INSTALL_RESULT.md`.
`XNU2LOG.BIN` sha256 `81a12aca82e5869962a6d0ec1ea60141ea5ed174c300fdc432ce1d51869a4a83`, NABULOG2 seq 1760, CRC valid, 0 bytes lost.

- 463 s of runtime, eight cores, SpringBoard / backboardd / runningboardd alive (`sample_ok`, one incarnation each).
- `NativeAdrenoA6xx: Metal accelerator published chip=06040001`.
- Display: `client-calls=0`, `swaps accepted=0`, `vsync sent=0`; GPU `scanout offered=0 done=0`.
- Frontend verdict, unchanged from sample 10 to 43: `M s0 c0 r0 i0 q167 k4/11 p15/8 F1 6607 the completed handler ru...`
- QuartzCore rows: `tile_downsample_1/2/4 Compile(NeedsInput(TileAttachments))`.

## Cause
`F1 6607` = one failed frontend check after step 0x6607, i.e. check 7 in `bridge/FrontendChecks.h`:
"the completed handler runs for a failed command buffer". It reads the handler's flag directly after
`waitUntilCompleted`. The completion-wait fix (correctly, per Metal's contract) stopped `waitUntilCompleted`
from waiting for handler delivery, so the flag can still be false.

`NativeMetalBridgePhase.h` starts the scanout client only when no frontend check failed:
`scanout = ok && job->frontendRan && !job->frontend.failed && gDevice;` - so this one check kept GPU scanout off
for the whole boot. Check 6 had the same race and passed by timing.

## Fix
`ci/build_combined_metal_checkfix.py`: checks 6 and 7 wait up to 2 s on a semaphore signalled by the completed
handler. The handler must still run; delivery is no longer assumed synchronous. FrontendChecks.h sha256
`1871c4649d30ce7b99056c2fb8b48f4dc1256dd0a60d38a80fc348b3186b84b5`.

- Build: run 42937996971 (`build-nabu-metal-runtime.yml` on this branch): `ASYNC_METAL_FRONTEND_HOST_PASS 20`,
  `FRONTEND_CHECK_FIX_APPLIED`. No GPU render test in CI.
- `ci/prepare_checkfix_metal_payload.py`: `CHECKFIX_METAL_PAYLOAD_HOST_PASS`, built on the pre-combined trust cache.
  - addon `e3dbd436fea3b782e25952fc1c36a9305bee4495e458e343be8fc690c7308a4f`
  - trustcache `496ac87e24ae207efe540ef01e49564ec863abfc249c57ce1c11bb5ade783efb`

## Installed
Only `kernel-fulltrace-panic.macho.gpuaddon` and `.trustcache` were replaced (temp copy, hash check, rename,
read-only readback). Kernel, ADT, menu and Data unchanged. Rollback:
- ESP: `*.gpuaddon.pre-combined-20261110` / `*.trustcache.pre-combined-20261110` (pre-combined).
- PC: `build-artifacts\esp-inputs-20261111\in-combined.*` (the combined pair this replaced).

Booted with `fastboot boot MiPad5.UEFI-v2608.03_nSB.img` (RAM only).

## Still open
If scanout now starts, `client-calls=0` (backboardd never called the IOMFB user client) and the QuartzCore
`TileAttachments` compile failures are the next leads. Persistent Data, Wi-Fi, audio and power remain unimplemented.

## Result on hardware (XNU2LOG seq 1872, CRC ok, 0 bytes lost)
The fix worked for what it targeted; the screen still showed the frozen DarwinBoot/menu text.
- Frontend verdict `M s0 c0 r0 i0 q167 k4/11 p15/8 F0` (was `F1 6607`); scanout client `P4 e0` = serving.
- backboardd (pid 73) now opens IOMFB: `client-calls=5`, notifications `subscriptions=86`, VSYNC `armed=1 sent=8301` (all 0 before).
- Still `swaps accepted=0`, `validation-calls=0`, scanout `offered=0`: backboardd never submits a frame.
- Before stopping, backboardd calls 12 IOMFB selectors the legacy framebuffer does not implement
  (`previous=e00002c7`, selector 15 `e00002bc`): 57, 15, 22, 29, 33, 79 (out 1580 B), 74, 12, 79 (44 B), 27 (3084 B), 84, 50.
  `nabu-iomfb-compat=1` answers them with placeholder data. After selector 50 nothing more is called.
- Ruled out: tile-shading kernels. The plugin offers only Apple1-3 families and `supportsTileShaders` = NO, so the
  `tile_downsample_* NeedsInput(TileAttachments)` rows are self-test-only.

## Next blocker
Real answers for the iPadOS 17.7 IOMobileFramebuffer selectors above (structure layouts of selectors 27/79/74 in
particular), so CoreAnimation accepts the display and starts swap_begin/swap_submit. This needs reverse engineering of
the 21H16 IOMobileFramebuffer user-client ABI and several boot iterations; it is not a one-step change.
