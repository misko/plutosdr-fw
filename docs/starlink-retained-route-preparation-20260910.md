# Retained route observation preparation — no checkpoint selected

This is an additive route-only Tcl proposal. No vendor command or real DCP
reader was invoked, and no synthesized checkpoint/hash has been selected.
The running parent-owned synthesis inputs remain unchanged.

Runner: `hdl/library/starlink_pss_acquisition/retained_output_actual/route_retained_output.tcl`.
Arguments: `SOURCE_DCP EXPECTED_SHA NEW_OUTPUT`. Parent must independently audit
the exact synthesis result, source/generic/constraint identities, diagnostics and
DCP hash, then separately authorize that one hash. The Tcl cannot discover or
choose a checkpoint. Its supplied hash is an identity check, not approval itself.

It retains the old `opt_design`, `place_design`, `phys_opt_design`, `route_design`
sequence without directives, two threads and the inherited 100/175 MHz clocks.
It adds no clocks, exceptions, groups, multicycle paths or constraint reads.
Immediately after routing, it writes and hashes the routed checkpoint, before
reports. A report failure remains failure while preserving the checkpoint.
All four clock pairs receive max/min top-20 reports, path counts and worst-path
slack/endpoints; missing intra-clock paths fail, empty cross-clock groups are
explicit. Global/unconstrained timing, route status, utilization/hierarchy,
clocks/interaction, exceptions, inherited XDC, verbose timing checks and CDC
are recorded. Original/routed DCP and original/copied runner hashes are checked
after success or failure. The original tool error is preserved ahead of any
post-integrity error. Terminal completion never means physical release or a
nonnegative timing result.

Eight local Tcl-stub tests passed in 0.08 s, terminal 0. Evidence:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-route-prep-v1.FpdLz4QW`.
The fixtures explicitly contain `OFFLINE_STUB_NOT_A_DCP`; no FPGA tool parses
them. Tests cover hash/path/no-overwrite admission, exact implementation order,
all eight path groups, preserved checkpoint on report failure and detection of a
mutated dummy source. A negative stub slack remains an observation, not a pass.

Proposed one-shot owner: parent-only, unique absent non-`/tmp` owner/output and
external log/journal paths; Vivado 2022.2 with SuSE `LD_LIBRARY_PATH`, two threads,
fixed reviewed process-group deadline (proposed 1200 s), no retry. Log and journal
options precede `-tclargs`. Pin the runner plus the separately approved synthesis
DCP hash, capture all original exits and before/after integrity, preserve all
products on failure, and independently inspect complete routing/timing evidence.
This document authorizes no invocation, timing waiver or deployment promotion.
