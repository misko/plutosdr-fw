# Exact retained-runtime synthesis preparation

Prepared only; **no synthesis or route was invoked in this lane**.
Final targeted offline gate: 25 passed in 1.15 s, original 80948 terminal 0.
Tested FW `2a57f89b2b3099b319ac2897db974a6674abf1ec`;
HDL `9bf22cbc5eae16f5281e7aa8742169fc86bed618`.

Prepared directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-output-synthesis-prepared-v2`.
External `SHA256SUMS` SHA:
`4a0bbd1b07ea94c51e5b001dbbd7c48b601d1abd8659253a318e3d3f6d357ecb`.
There are 93 files plus the inventory. The existing v5 qualified bundle and its
unchanged frozen CLI remain the runtime/source/result authority; no new generic
bundle framework or numerical checker was introduced.

The copied runner `synthesize_retained_output.tcl` SHA is
`79aca85d52146627a2584fa2d3443ead35492ecfc279f156717794535f67f660`.
Its two arguments are `EXPECTED_PREPARED_SHA NEW_ABSENT_OUTPUT`; its own absolute
location selects the prepared input directory. Parent owns the one-shot process,
external logs/journal, timeout and final execution review. No route is implicit.

The runner uses the exact 16 qualified runtime files as SystemVerilog in
`sources_1`, the enabled retained top plus exact R1/B1/O1/L1, original kernel/FFT
factory, original literal 100/175 MHz XDC with no clock groups or timing exceptions,
the prior OOC part/directives/control-set threshold/thread hook, and two threads.
It records generated-IP before/after identity, all eight clock-pair max/min path
reports, global/unconstrained timing, CDC, exceptions, clock interaction, effective
XDC path/hash/scoping/use properties, hierarchy and resources. The DCP is written
and hashed after successful synthesis/black-box/clock checks, before observational
reports. A report failure still fails the run while preserving that checkpoint.
Original failure status and original/copy/IP/DCP post-checks are retained.

Tests: `tests/test_starlink_retained_output_synthesis.py`, using cache-disabled
PPU-venv Python `-B`, cleared Python/library variables, unique recovery TMPDIR,
basetemp and XML/log paths. Raw evidence:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-synthesis-prep-tests-v2.B1pDETdY`.
Tests exercise source/digest/clock/argument/no-overwrite admission, copied-source
faults after an executed Tcl create-project stub, sanitized child environment,
exact generic/clock fragments, and 16-file selection. The stubs never create a
vendor project. Ruff F/E9 passed.

The first 22-test gate and v1 package remain intact (`67dda100...`, FW590ea2e74).
Parent source review found that a new preparation output nested inside qualified
input could recursively copy itself. V2 adds an early rejection for children of
qualified, actual and source roots, plus three tests proving no child was created.
This was a copier admission finding, not a runtime or vendor failure. Runner,
qualified v5 sources, vectors, clocks and acceptance limits remained unchanged.
