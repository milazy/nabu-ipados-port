# Memory headroom and UI observer repair - 2026-11-10

The current standard-compositor build was read back from temporary nabu recovery. Its valid NABULOG2 snapshot has SHA-256 `f67c0ff0d195b25b2d16dd0b17f53f9de2f3b739ebcc28222d41b30ef54f6e02`, sequence 743, boot ID `ad987415000000002f02000000000000`. The recorded kernel timestamp is 2026-11-10 02:02:34 UTC and the selected standard-addon/UI-watch flags match the installed `dc260d7980a9f0baadd8730f14e3659fa1975c88ab8d917f14851c21055037a4` build.

## What the new device log establishes

- Standard addon: eight files written, zero failures, error 0. Extensions and daemon views both reach checked stage 5, status 0.
- GPU accelerator publishes. The display timer starts at 60 Hz and sends 29093 VSYNC notifications by the final sampled state.
- Accepted swaps, transfers and retired frames remain zero. There is still no visible iPadOS UI.
- There are 108 exit-reason records in namespace 1/code 4 and 19 in namespace 1/code 14. The pinned XNU header identifies these as `JETSAM_REASON_MEMORY_VMPAGESHORTAGE` and `JETSAM_REASON_MEMORY_SUSTAINED_PRESSURE` respectively.
- The bootstrap records 217486 free plus 44658 wired pages: 262144 total. The native 4 KiB ABI patch selects 4 KiB software pages, corresponding to the loader's 1 GiB window. TWRP on this physical device reports `MemTotal: 5594820 kB`.
- No `NabuUI` event or sample records appear. This is an observation gap, not evidence that SpringBoard never ran or is healthy.

## Memory contract finding

The exact live ADT, SHA-256 `658e38300dfd05e9a8c03e4c44790192c313949b627c72dfdb9144c7c889f12c`, requests only `0x40000000` bytes in `/chosen/darwinboot-memory-size`. DarwinBoot assigns both boot_args memory-size fields from this allocation, and pinned XNU `arm_vm_init` derives managed physical memory from those fields. The separate ADT `dram-size` does not enlarge that allocated window.

`ci/prepare_nabu_memory_window.py` changes the requested allocation to 2 GiB (`0x80000000`). It changes one byte, at file offset 847, and preserves every other property. The independent ADT decoder checked 79 properties and found only that difference. Prepared ADT SHA-256: `0b6e519bf5b187fe5c311639f4b121a91dce820e25aaeba29a0525fd0d443b69`.

This is a request for a real reservation: the existing loader must successfully allocate a conventional-memory run with UEFI AllocatePages before handoff. No allocation bypass or declaration of unreserved RAM is introduced. Successful 2 GiB allocation and UI progress remain device checks, not host-proven outcomes. This addresses an observed bottleneck; it does not establish memory pressure as the only UI failure.

## Observer finding and source correction

The previous standard-addon change installed the UI snapshot callback, but `NativeAdrenoService.cpp` installed the outer writer poll only when `nabu-gpu-userprobe=1`. That runtime flag selects a different, incompatible addon transport, so it is intentionally absent. Consequently the UI events were never drained into the capture.

`ci/nabu-ui-writer-sampling.patch` enables the existing bounded software-state writer poll when either the probe or UI-watch flag is selected, retaining the probe-policy setting itself. It adds one explicit startup marker; the backend verifier requires it. Runtime continues to use the standard addon and `nabu-ui-watch=1`, without selecting the closed probe transport.

Kernel build: https://github.com/beamerwz/nabu-ipados-macos-build/actions/runs/42804872252 , source head `c5bfce314b490249e03ae4319405293f82f12c07`. The same verified pass-one reference is reused. The build completed successfully, including Mach-O, backend and display-layout gates. Artifact `13758179652` was downloaded and its ZIP SHA-256 matched `67f7b96f91ac820500acb953addf82fb18437ef537858ac926a0dc394d3cc546`. The extracted kernel matched its paired report: `b847c2034d79e2aad9c57bed094438318e828ddcecb3f2af57855bdf0d4ae255` (124399616 bytes).

Owner ZAP identity preparation produced kernel `e522b69aeaf901bc0188a79ed4860c3608a980021833a33a95ff65ab4a3c3b97`. Structural validation and the three executable signed-page/trust-cache checks passed. Installation completed at 11:33:42 UTC with receipt `MEMORY_UI_INSTALL_PASS_BOOT_UNVERIFIED`. The kernel, 2 GiB ADT and menu were written and read back; final menu SHA-256 is `af0703e2a1d10e2a9dde75fa23facb77a0d4d8faacda5c8c73143b0e9b3f3b0c`. Protected trust cache, addon and packed Data hashes remained unchanged.

`scripts/reboot_memory_ui.py` independently rechecked all six fingerprints, nabu/recovery identity and the read-only ESP block state. One ADB reboot request was accepted at 11:34:02 UTC (12:34 Rome). Its receipt is `FINAL_READBACK_PASS_REBOOT_REQUEST_ACCEPTED_UI_UNVERIFIED`. Actual UEFI allocation, reduced memory pressure, UI process progress and visible iPadOS remain unverified until the next device observation/readback.

`scripts/install_memory_ui.py` stages and verifies the new/rollback kernels, ADTs and menus in RAM, selects the independent fallback before replacement, then verifies each write and returns the ESP to block-read-only. The paired trust cache, standard addon and packed Data are protected. It checks the exact previous live fingerprints and the independent memory report. This installation changed only the ESP kernel, ADT and menu; it did not write Android images, GPT or Apple OS/Data partitions.

## Follow-up device confirmation

The next CRC-verified readback, sequence 862, confirmed 475607 free plus 48681 wired 4 KiB pages (2 GiB total), successful UI process activation and no recorded namespace-1 memory-pressure exits through the committed snapshot. Visible UI was still absent. See [the frontend repair record](METAL_FRONTEND_REPAIR_20261110.md) for the exact capture identity, remaining zero-frame behavior and the subsequently installed async-only Metal repair.
