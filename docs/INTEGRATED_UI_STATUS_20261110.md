# Integrated nabu UI repair - 2026-11-10

The corrected kernel compiled, passed independent host validation, was installed with verified readback, and received one reboot command at 01:36 UTC. Visible SpringBoard and frame presentation are still unverified. ADB disconnected after reboot; that establishes neither success nor failure of XNU.

## Build and validation

Canonical repository: `beamerwz/nabu-ipados-macos-build`, branch `build/nabu-integrated-vsync-20261110`. The account transfer retained the reference artifact and owner policy assets and cleared runner allocation. No recurring monitoring was scheduled.

Run: https://github.com/beamerwz/nabu-ipados-macos-build/actions/runs/42734654454

The compile, final link and prelink completed successfully. The workflow as a whole failed an obsolete string check for `offline-legacy-transfer`, which belongs to the older vendor backend. The selected `platform/NabuLegacyCpuPresent.cpp` implements its own swap validation and presentation queue. This is not a green CI run.

`ci/verify_cpu_display_backend.py` replaces that stale check with compiled markers and defined executable methods for swap validation, queue handling and VSYNC, plus graphics startup definitions. It passed on the downloaded raw artifact. `ci/verify_display_reference.py` and `ci/verify_xnu_macho.py` also passed. These are static checks, not proof of bootability.

- Raw compiled kernel SHA-256: `0759be3415a04a3966af2006c962dc9dded97660dc7fdaac2056ca3f3eaafdda`
- Installed kernel SHA-256: `544f45311168ba5a92f9e1b3070077b6c92fca41df5eb8c1106e1f6ccbacbc50`
- Kernel size: 124399616 bytes
- Installed menu SHA-256: `21f6887c55be6611a67c22e6ac8d885b1757015ab1dbb1d54672ead7bb21aa83`

Preparation changes one public owner ZAP metadata digest after validating the original kernel. It does not change code or layout. Local preparation and installation receipts retain both identities and explicitly record `boot_verified: false`.

## Repairs included

The workflow now preserves and hash-checks both `pass1/kernel.macho` and its matching `kernel.json`. Final display binding requires both. It can reuse the exact pass-one artifact from run `42727406285`, SHA-256 `606571c37363bfcc477ad881272793d35a57c61b32786ec1b18fbe9a7fe63762`.

`ci/stage_graphics_startup.py` retains prepared BSD/IOUserClient startup code while omitting conflicting console hunks. This resolves the three formerly undefined graphics startup symbols. The final link now succeeds.

The candidate includes the ported 60 Hz VSYNC path and GPU scanout. The active entry retains scale 2, keybag notifications/state, the watchdogd and Setup Assistant policies, and `-no_corpses`; it selects `sheng-vsync=60 nabu-gpu-scanout=1 nabu-cpu-diff=0`. Obsolete vendor-only validate/transfer/CPU-present flags were removed. `sheng-vsync-fixed` is absent because this backend does not implement it.

## Device installation

The guarded installer checked recovery/device identity, battery, original menu/kernel/ADT/Data hashes, space and rollback inputs. Both new and rollback kernels were staged and checked in RAM. It preserved the old menu and selected the existing fallback before replacing the experimental kernel slot, checked readback, then activated the final menu. Final independent readback matched both installed hashes and confirmed block-read-only ESP before reboot.

The active entry remains `xnu-existing-ui-policy`; its title identifies the integrated rebuild as unverified. The fallback remains `xnu-crypto384`. The old menu is preserved as `unixnu.pre-integrated-ui-20261110.toml`, and the old kernel is retained on the PC. ADT, packed Data, Apple partitions and Android GPT were unchanged.

Local receipts: `build-artifacts/nabu-integrated-ui-final-20261110/live-install-receipt.json` and `reboot-receipt.json` under the lab root. The latter records only acceptance of the reboot command.

## Evidence from the preceding kernel

Earlier launchd/OwnerData startup reached a running kernel but zero presented frames. A previous capture recorded SpringBoard traps mapping to the FrontBoardServices assertion `FBSDisplayMode cannot be configured as requested : %@`; this establishes display-mode validation failure without identifying one invalid field.

The subsequent existing-kernel policy test used the six supported settings, confirmed by its captured 712-byte boot command. Its CRC-verified log SHA-256 is `8e1e979f1c8d6a7cf44fd7a6c636c475437f1eac80ea5bf9340ffee7fa7d00bc`, committed sequence 492.

| Observation | Existing-kernel policy test |
|---|---|
| Startup | launchd and OwnerData mount reached |
| Duration | display status at 420 seconds |
| GPU | command-processor fence proof; accelerator publishes |
| Keybag | state calls succeed; 43 subscriptions, status 0 |
| Display | 0 accepted swaps, 0 transfers, 0 retired frames |
| SpringBoard | no captured exception/exit; health unproven |
| backboardd | 16 calls, 12 errors; some may be capability probes |
| Other failures | 15 ScreenTimeAgent signalled exits |

`-no_corpses` suppresses normal corpse reports. A zero crash-message count cannot establish process health. The previous kernel ran behind the unchanged coloured bars/menu. This supports testing the rebuilt presentation path, but does not establish VSYNC as the only remaining issue.

## Remaining verification

Observe the tablet after this reboot. If the menu remains, recover one fresh log and compare startup and accepted/presented frame counters against the preceding capture. Confirm sustained visible SpringBoard before reporting UI success. Full App Store, networking, audio, persistent Data and 120 Hz operation remain unproven.
