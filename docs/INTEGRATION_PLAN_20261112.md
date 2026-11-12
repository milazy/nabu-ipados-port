# Integration plan, from batch 5 on

Until now we fixed one symptom per batch. From now on each subsystem is ported whole from a donor that
already works on the same hardware or the same framework, and every batch carries several subsystems,
each behind its own boot switch so it can be turned off on its own.

## Donors

| Donor | Why it matters | License |
|---|---|---|
| `dipa-studio/sd855_ios26` (Pixel 4 / Realme X2 Pro, **same SoC SM8150, Adreno 640, WCN3990**) | Working Wi-Fi in Settings (IO80211 over wland), audio over ADSP, display dimming, ~53 fps GPU swapchain, App Store/IPA layer | MIT |
| UniXNU sheng (`UniXNU/UniXNU-sheng`, same framework as ours) | Apple80211 user client on en0 (`package/WifiNet.cpp`, legacy layout = iPadOS 17/26), AppSync, Bluetooth runtime, audio HAL, launchd cache | BSD-2-Clause-Patent / GPL-3.0 (AppSync) |
| UniXNU nabu (`zzweiqing/UniXNU-nabu`) | Our board base: display, touch, GPU, UFS | upstream |

## Subsystems → source → nabu delta

| Subsystem | Port from | nabu-specific work |
|---|---|---|
| Wi-Fi in Settings | sheng `WifiNet.cpp` (Apple80211 ioctls, legacy layouts) + sd855 `flame_wlan.c` (`/dev/wlan` bridge that our wland already speaks) | Glue `nw_abi` to `/dev/wlan`; check 21H16 IO80211 layouts on device |
| Shell / SSH | dropbear (Procursus) as launchd-cache job, trust-cached | Network over wland; this removes most TWRP trips for logs |
| IPA install | AppSync (batch 4, done) | Hardware check |
| Display fps | sd855 `gpu_direct` swapchain vs our handoff (85 ms copy) | Measure on nabu panel (dual DSI 2560×1600) |
| Brightness | KTZ8866 over GENI I2C + sheng `BacklightMode.m` | New driver |
| Audio | sd855 ADSP path + sheng audio HAL | nabu amps/codec differ: DTS survey |
| Bluetooth | sheng QcaBluetooth design (WCN3990 BT over UART) | UART/GPIO from nabu DTS |
| Sensors, battery, sleep | sd855/sheng where SoC-level | PMIC and fuel gauge from DTS |

## Working method

1. One CI pipeline produces kernel + userland + launchd caches + addon list; the PC script installs everything in one trip.
2. Each subsystem gets a boot-log marker and a boot switch; `docs/STATUS_*.md` records compiled / attached / end-to-end.
3. Once SSH works, testing happens live on the tablet instead of one TWRP trip per log.
