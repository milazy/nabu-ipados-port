#!/usr/bin/env python3
"""Enable a one-shot _arm_init entry PSCI reset in a COPY of pinned UniXNU code.

No disk operations or installer. The probe is intentionally temporary:
blue at kernel entry, magenta near SCTLR_EL1, then reset ONLY if _arm_init
entry is reached. Source is immutable except inside a transient CI checkout.
"""
import hashlib
from pathlib import Path
import sys

p=Path(sys.argv[1])
original=p.read_bytes()
PIN="159eb1ea8d6c1da30f26913a281f46e21d940a1ae7886656529907ec3edf96ad"
if hashlib.sha256(original).hexdigest()!=PIN:
    raise RuntimeError("Pinned UniXNU entry-probe source mismatch")
old=b"""        call_va, callee = find_call(data, symbols, args.function, args.reset_after, args.occurrence)
        sites.append((call_va, 4, {'callee': callee, 'target': call_va + 4}))
        description = f'stage 4 reset {"before" if args.reset_before else "after"} call #{args.occurrence} to {args.reset_after} in {args.function} (at {call_va:#x})'"""
new=b"""        if args.reset_after == '__arm_init_entry__':
            if args.function != '_arm_init' or not args.reset_before:
                raise SystemExit('arm_init entry probe requires --in _arm_init --reset-before')
            call_va = kernel_names.get('_arm_init')
            if call_va != 0xfffffff00bf0c730 or word(call_va) != 0xd10343ff:
                raise SystemExit('Exact owner-root _arm_init entry opcode/address guard failed')
            sites.append((call_va, 4, {'target': call_va + 4}))
            description = f'immediate PSCI reset at _arm_init entry {call_va:#x} (no timer)'
        else:
            call_va, callee = find_call(data, symbols, args.function, args.reset_after, args.occurrence)
            sites.append((call_va, 4, {'callee': callee, 'target': call_va + 4}))
            description = f'stage 4 reset {"before" if args.reset_before else "after"} call #{args.occurrence} to {args.reset_after} in {args.function} (at {call_va:#x})'"""
if original.count(old)!=1:
    raise RuntimeError("Unique pinned source block not found")
p.write_bytes(original.replace(old,new))
print("ARM_INIT_ENTRY_SOURCE_GUARD_PASS")
