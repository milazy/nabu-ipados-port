# Integrated nabu UI repair — 2026-11-10

Status: build in progress; new kernel has not been installed or booted.

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

No full App Store, networking, audio, persistent Data or 120 Hz operation is claimed. The Pad 7 macOS project uses a different SoC/GPU and cannot supply interchangeable firmware for this Pad 5.
