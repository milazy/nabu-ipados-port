#!/usr/bin/env python3
"""Replace only UniXNU's stage-3 *delayed* PSCI reset body with its already
reviewed *immediate* PSCI reset body, in a temporary CI source checkout.

This probe tests whether execution reaches the first instruction after
SCTLR_EL1/ISB. It must NOT read CNTVCT_EL0 and has no timer dependency.
"""
import hashlib
import pathlib
import sys

src=pathlib.Path(sys.argv[1])
original=src.read_bytes()
expected_sha="159eb1ea8d6c1da30f26913a281f46e21d940a1ae7886656529907ec3edf96ad"
if hashlib.sha256(original).hexdigest()!=expected_sha:
    raise RuntimeError("Upstream pinned XNU entry-probe source changed")
anchor=b"def kernel_symbols(kernel):"
if original.count(anchor)!=1:
    raise RuntimeError("Missing unique function anchor in upstream probe source")
insertion=(b"# Specific immediate post-MMU physical diagnostic only.\n"
           b"# Reuse existing validated RESET_BEFORE assembler with no timer reads.\n"
           b"SOURCES[3] = RESET_BEFORE\n\n\n")
modified=original.replace(anchor,insertion+anchor)
src.write_bytes(modified)
print("INSTANT_POST_MMU_SOURCE_GUARD_PASSED")
