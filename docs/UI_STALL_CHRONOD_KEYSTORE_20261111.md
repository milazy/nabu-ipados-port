# UI stall: SpringBoard → chronod → IDS → AppleKeyStore key wrapping (2026-11-11)

## Symptom

iPadOS 17.7 (21H16) on nabu reaches launchd, SpringBoard and backboardd. backboardd opens IOMFB, gets
VSYNC and the Metal frontend passes its checks, but no swap is ever submitted and the panel keeps the
boot text.

## Evidence

Diagnostic kernels sample the user stacks of selected processes (`ci/apply_ui_stack_sampler.py`,
`ci/apply_ui_targets_chronod.py`). Symbolization runs on GitHub Actions against the dyld shared cache
from the full iPad7,11 21H16 IPSW (`.github/workflows/symbolize-stacks.yml`, macOS runner).

| Log | Process | Where it waits |
| --- | --- | --- |
| seq 2128 | backboardd main | `CFRunLoopRun` idle: the render server waits for work |
| seq 2128 | SpringBoard main, samples 11-19 | LaunchServices context lock (`_LSContextInitCommon`), resolves later |
| seq 2128, 2270 | SpringBoard main, sample 23 to end | `xpc_connection_send_message_with_reply_sync` ← `-[CHSChronoServicesConnection _subscribeToExtensions]` ← `-[CHSWidgetExtensionProvider registerObserver:]` ← `-[SBHIconManager init]` ← `-[SBUIController init]` ← `-[SpringBoard _completeStartupAfterMainSceneConnect:]` |
| seq 2270 | chronod main | ActivityKit initialisation (`dispatch_once`) |
| seq 2270 | chronod IDS queue | `dispatch_sync` inside IDS.framework |
| seq 2270 | liveactivitiesd main | `-[_CDClientContext objectForContextualKeyPath:]` synchronous NSXPC reply |
| seq 2270 | liveactivitiesd worker | `IDSCopyLocalDeviceUniqueID` |
| seq 2128, 2270 | kernel | `NABU AKS sel=10 rc=0xe00002c7` on every call: `aks_wrap_key` unsupported |

SpringBoard never completes startup, so it never commits a scene and backboardd has nothing to
composite. UniXNU's venus record describes the same chain (liveactivitiesd → chronod → SpringBoard,
`SWAP=0`).

## Cause

nabu answers AppleKeyStore with its own `platform/NabuKeybagNotifications.cpp`, a copy of UniXNU
AppleKeyStoreState 42ff83e. That version answers only state queries. Keychain item creation needs
`aks_wrap_key`; without it IDS cannot create its identity and every client of IDS waits.

UniXNU AppleKeyStoreState 5454637 (2026-11-06) adds software key wrapping "so the keychain can store
and read items".

## Fix

`ci/apply_aks_keywrap.py` ports that change to nabu's user client: selectors 10 (wrap), 11 (unwrap),
23 (bag UUID), 40 (generation) and 160 (cache flow), with the upstream SHA-256 construction. The device
key derives from `/chosen unique-chip-id` when present, otherwise from a fixed label; nabu's Data volume
is a RAM block recreated at every boot. This is software wrapping, not hardware data protection.

Host test: wrap/unwrap round trip, a modified blob is rejected, SHA-256("abc") matches the standard
vector.

## Rollback

Only `Payloads/kernel-fulltrace-panic.macho` is replaced. Previous kernels on the PC:
`build-artifacts\nabu-stack-chronod-43065933688\kernel-stack-chronod.macho` (5d469dce…),
`build-artifacts\nabu-stack-sampler-20261111\kernel-stack-sampler.macho` (4fa71f9d…),
`build-artifacts\esp-inputs-20261111\in-kernel.macho` (7291773…).
