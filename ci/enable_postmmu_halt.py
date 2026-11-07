#!/usr/bin/env python3
"""Build an exact, non-resetting post-MMU control in a temporary UniXNU checkout.

The original source is SHA-pinned, no source or kernel in this repository is
modified, and the resulting copy hangs after the MMU checkpoint without
requesting PSCI reset, accessing CNTVCT, or writing storage.
"""
import hashlib
import pathlib
import sys

source=pathlib.Path(sys.argv[1])
original=source.read_bytes()
PIN="159eb1ea8d6c1da30f26913a281f46e21d940a1ae7886656529907ec3edf96ad"
if hashlib.sha256(original).hexdigest()!=PIN:
    raise RuntimeError("Expected pinned UniXNU entry probe source")
anchor=b"def kernel_symbols(kernel):"
if original.count(anchor)!=1:
    raise RuntimeError("Expected unique kernel_symbols anchor")
insertion=b'''# POST-MMU NEGATIVE CONTROL: do not call reset, do not access timer.
# WFE followed by backwards branch. The CPU stays at this exact checkpoint.
SOURCES[3] = """.text
.global _start
_start:
1:
  wfe
  b 1b
"""

'''
source.write_bytes(original.replace(anchor,insertion+anchor))
print("POSTMMU_HALT_SOURCE_PIN_VALIDATED")
