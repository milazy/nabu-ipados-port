# Integrated nabu UI repair — 2026-11-10

Status: corrected kernel rebuild remains blocked by GitHub billing/spending restrictions. At the owner's later request, the already-installed kernel was retained and its supported UI policies were activated in a separate backed-up menu entry. The menu installation and unchanged payload hashes were verified, then one tablet reboot was accepted. Hardware UI outcome is pending observation.

Blocked retry: https://github.com/yeahyeah97/nabu-ipados-macos-build/actions/runs/42731389168 . GitHub reports: “The job was not started because recent account payments have failed or your spending limit needs to be increased.” No payment setting or spending limit was changed.

## Verified current failure

The saved NABULOG2 capture dated 2026-11-09 22:02 UTC has a valid committed slot and records launchd and OwnerData mounting. The A640 reaches its command-processor scratch/fence proof and `state=ready`, but the display accepts and retires zero frames. This is not an interactive iPadOS boot.

SpringBoard repeatedly traps at runtime PC `0x1a5b00744`, with the recorded shared-cache slide `0x6780000` and UUID `5eb3de32eed3377b9a3b572b08c888cf`. Removing that slide maps the PC to `FrontBoardServices + 0xf744` (`0x19f380744`) in the original 21H16 cache. The surrounding code reaches the assertion whose format string is `FBSDisplayMode cannot be configured as requested : %@`. This establishes a display-mode validation failure, but does not identify which individual mode field was invalid. The live ADT contains no `/chosen/display-scale` or display rotation property.

The prepared menu enables the existing phase-4 scale policy with `offline-legacy-unit-scale=2`, keybag notifications/state, the opt-in watchdogd and Setup Assistant policies, GPU scanout, and the newly ported 60 Hz VSYNC path. These are candidates for hardware verification, not proven fixes. `sheng-vsync-fixed` was removed from the installer because the selected CPU presentation source does not implement that option.

## Build repairs

The old two-pass workflow lost `pass1/kernel.json` while copying `kernel.macho`. Final display binding derives relocated addresses from both files and consequently failed with FileNotFoundError. The workflow now copies both, checks the report hash against the kernel and retains both as artifacts.

The first rebuilt pass-one candidate completed with SHA-256 `606571c37363bfcc477ad881272793d35a57c61b32786ec1b18fbe9a7fe63762`. The final link then exposed that the old bootstrap merge helper excluded the prepared graphics startup patch, leaving `nabu_graphics_start_after_root`, `nabu_graphics_worker_stage` and `native_mobile_graphics_load_status` undefined. `ci/stage_graphics_startup.py` now retains the prepared BSD/IOUserClient code and omits the conflicting console hunks; the filtered patch and its late-start companion passed application checks against pinned XNU. The workflow can reuse the exact hash-checked pass-one artifact and rebuild only the final stage. It now runs by explicit dispatch.

`ci/verify_display_reference.py` verifies the final and pass-one report/image identities, the exact 21H16 original cache identity, slide, and all segment virtual addresses/sizes for IOMobileGraphicsFamily and IOSurface. A shifted display address is rejected. Run this on unmodified compiled kernels before applying the owner ZAP metadata digest adjustment. This is a static layout gate, not evidence of bootability.

The device installer still checks device/recovery identity, battery, all expected live hashes and rollback inputs. It stages both kernels in RAM, sets the preserved fallback before replacing the experimental slot, verifies readback, then activates the candidate. It preserves Apple OS/Data payloads and the partition layout. Boot command length must be below DarwinBoot's 1024-byte buffer.

## Remaining verification

1. Finish both build stages and inspect the final outcome and prelink records.
2. Run Mach-O and postlink display-reference validation.
3. Apply and verify the owner firmware digest adjustment; verify the final menu and protected payload hashes.
4. Install once with rollback guards, then reboot once.
5. Confirm sustained visible SpringBoard and presentation progress. Compilation or provider registration alone does not establish success.

The nine patch sections affecting BSD startup and IOUserClient apply together to pinned XNU, and all three missing definitions appear exactly once. A broader exploratory flat-patch dry run encountered unrelated carrier/union ordering issues; it does not establish that the complete staged build succeeds. The decisive remaining check is the macOS CI rebuild.

After the account restriction is resolved, resume explicitly (no monitoring or automatic retry was scheduled):

```powershell
gh workflow run build-nabu-integrated-ui.yml --repo yeahyeah97/nabu-ipados-macos-build --ref build/nabu-integrated-vsync-20261110 -f reference_run=42727406285 -f reference_sha256=606571c37363bfcc477ad881272793d35a57c61b32786ec1b18fbe9a7fe63762
```

No full App Store, networking, audio, persistent Data or 120 Hz operation is claimed. The Pad 7 macOS project uses a different SoC/GPU and cannot supply interchangeable firmware for this Pad 5.

## Existing-kernel UI policy test

The active test entry is `xnu-existing-ui-policy`. The unchanged kernel SHA-256 is `2a7430ce4f5a0da25fa0005063bd283db7c528b05b69ac94e13262dd669a3d9a`; installed menu SHA-256 is `8523904268023a7493e28957dd9767506836217ee21dd714f77ecf34b0dc9fe2`. The previous menu is preserved as `unixnu.pre-ui-policy-test-20261110.toml` on the ESP and as a PC copy.

Only supported existing-kernel options were enabled: `offline-legacy-unit-scale=2`, `nabu-keybag-notifications=1`, `nabu-aks-state=1`, `nabu-disable-watchdogd=1`, `nabu-skip-setup=1`, and `-no_corpses`. The new VSYNC implementation is absent from this kernel and was not enabled. Kernel, ADT, packed Data and OS volumes were not replaced. A reboot command was accepted after the verified install; this is not confirmation of a successful SpringBoard session.

## Fresh readback after the existing-kernel test

Recovery was started temporarily from Fastboot and the ESP was mounted block-read-only. The new CRC-verified capture is `NABU_NEWEST_LOG_20261110T011048Z.bin`, SHA-256 `8e1e979f1c8d6a7cf44fd7a6c636c475437f1eac80ea5bf9340ffee7fa7d00bc`, boot ID `c00b5d15000000009701000000000000`, committed sequence 492. The 712-byte boot command in the capture includes all six newly selected settings, confirming this run actually used them.

| Observation | Fresh capture |
|---|---|
| Apple startup | launchd and OwnerData mount reached |
| Duration | display status sample at 420 seconds |
| GPU | command-processor fence proof passes; Metal accelerator publishes |
| Keybag | state-client calls succeed; notification status 0, 43 subscriptions |
| SpringBoard | no captured exception/exit records; this does not prove a healthy UI |
| Display | 0 accepted swaps, 0 transfers, 0 retired frames |
| backboardd client | 16 calls, 12 returned errors; some may be capability probes |
| Other process failures | 15 ScreenTimeAgent signalled exits; optional services also exit |

`-no_corpses` suppresses normal corpse/crash-report messages, so the generic analyzer's zero crash-message count cannot establish that all processes are healthy. The independent exception/exit trace has no SpringBoard records in this snapshot. The remaining visible failure is presentation: the kernel ran behind the unchanged menu but no UI frames reached scanout. This supports testing the missing display timing path in the corrected rebuild; it does not prove VSYNC is the sole remaining cause.

A retry under the previous repository owner was rejected before runner assignment (run `42734123019`). The owner subsequently transferred the same private repository to `beamerwz/nabu-ipados-macos-build`; branch, reference artifact and policy assets were verified after transfer. The canonical Git remote now uses that owner. The tablet remains in recovery awaiting a validated new kernel.
