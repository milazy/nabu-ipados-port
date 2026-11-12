# nabu forks and related ports - comparison (12 Nov 2026)

Our boot base: zzweiqing/UniXNU-nabu 54b4f98 + this repository (RP-1, docs/RESTORE_POINT_20261112.md), iPadOS 17.7 21H16,
xnu-10063.141.1. It reaches Home, Safari and Settings on the owner's tablet.

| repository | history | OS / kernel | furthest state it records | useful for us |
|---|---|---|---|---|
| zzweiqing/UniXNU-nabu | our base (54b4f98) | iPadOS 17.7, xnu-10063 | SpringBoard UI, A640 Metal scanout | already integrated |
| 3214791900-del/unixnu-nabu-build | 417 commits, branches main + nabu-gpu-port (default), head 52ba9eb 11-12 | xnu-8796 (iOS 16 generation) | black screen; newest commits try to reproduce the zzweiqing build on Codemagic | nothing ahead of our base |
| lee-kenneth/unixnu-nabu | 104 commits, head 2b8bb29 10-23, same root 3f28f91 | iOS 16 line | CI and userdata image work | nothing ahead |
| Lux12138/unixnu-nabu | 182 commits, head 39cff5f 10-28, same root | iOS 16 line | launchd, SpringBoard running, black frames; NativeDwc3 behind nabu-usb=1 | USB (DWC3) reference for later |
| XingJiaoStudio/unixnu-nabu-sweet | 17 commits, head bef0949 11-05 | iOS 16.7.16, SWEET kernel from UniXNU-raphael (K20 Pro, SM8150) | CI only; no nabu boot recorded; needs an HFS+ root flashed over userdata (destructive) | not applied |
| zzc775/unixnu-nabu | not reachable (GitHub asks for credentials: private or removed) | - | - | - |

## The decisive reference: sd855_ios26 (IOS-26-Hot, SWEET line), same SoC and Wi-Fi family
README records Wi-Fi working: userland `wland` drives WCN3990 (QRTR + PD-Mapper wlan_pd + QMI WLFW + CE/HTT/WMI), WPA2/WPA3,
native Settings -> Wi-Fi through IO80211, on an SM8150 phone (Pixel 4 "flame"; iOS 26.5.2 23F84, xnu-12377).
Pieces:
- userland phone/wifi/ (about 7k lines): SCM PAS boot of MPSS, SMEM, SMP2P, GLINK, qrtr_mux, rmtfs, tftp, pd-mapper, servreg,
  WLFW, copy engines/HTT/WMI (ath.c, radio.c), link/ipnet/bridge, through /dev/pmem.
- kernel xnu/patches/0094 (sweet_pmem.c, sweet_files.c), 0102 (rpmh), 0123 (flame_wlan.c /dev/wlan, flame_sta.c,
  redwood_apple80211.c + redwood_net.c en0 for wifid, MiniIONetworkStack, RedwoodWLAN).
Port plan for nabu: same chip family (WCN3998 vs WCN3990), nabu carve-outs from the unit's FDT (mpss 0x8e000000/0x9600000,
wlan_fw 0x8bc00000/0x180000, rmtfs 3 MiB dynamic, smp2p-modem items 435/428 SPI 451 bit 14, glink modem SPI 449 bit 12,
rails pm8150 l1/l7, pm8150l l2/l11, cx.lvl, mss.lvl), WLAN-only modem image on modem_b (modem.mdt + b00..b22, wlanmdsp.mbn,
bdwlan.*). Kernel patches re-based from xnu-12377 to xnu-10063; Apple80211 bridge checked against iPadOS 17 wifid.
