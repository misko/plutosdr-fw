# Single-RX FPGA GLRT evidence

Experimental branch `codex/starlink-glrt-only-do-not-merge`. Persistent task
`01a0821a-7b4c-73f0-8b2c-47b4e95207f9`, gpt-6-astra / xhigh; goal active without
a token budget. See [the completion gate](GLRT_ONLY_GOAL.md).

## Source isolation, 2026-09-08

Firmware fork `7e20f6e5c693e8aa1a92b2dd3f918feffff722ad` verified. Independent
local clones were initialized at these gitlinks, each on its own experimental
branch. They share read-only Git objects with the reference through alternates;
their source and build directories are independent, with no working-tree symlinks.

| Component | Initial commit |
|---|---|
| HDL | `edb0f7070ac4fe01a9a08f9d7d98bc70d03114d4` |
| Linux | `5d706586c591d4c9f5fc8a308b2b248693c0d279` |
| Buildroot | `41a2a806d97ec04a4d92f3f96c9d6d973dc3c8e6` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a` |

No applicable AGENTS.md files were found in this firmware worktree or its
initialized components. Scanner reference instructions were read; its sources
are read-only and will not become runtime dependencies.

## Architecture under implementation

One pilot-centered RX1 source, with a free-running absolute source counter,
feeds both native-rate FPGA GLRT and an independent continuous 2.5 MS/s IQ
exporter. The new profile excludes the coarse and fine PSS IP entirely.
The exporter uses unity at 2.5, a final 5-to-2.5 FIR at higher rates, and an
additional 10/25/60-to-5 FIR where needed. Fixed pilot-centered tuning makes
the initial digital translation zero, explicitly recorded in the frequency plan.

Pilot-only FPGA acquisition proposes timing using known-pilot correlations;
a bounded native-rate sample ring supports 64-symbol exact/control GLRT.
The frequency search and score decision must run in fabric. CPU control cannot
provide acquired timing/CFO to the primary FPGA path. Numerical/resource work
will establish admission capacity and expose missed work before this design
is considered implemented. The proposed schedule is not yet a throughput proof.

## Qualification ladder

| Source MS/s | Numerical reference | RTL verified | Synthesized | Full route | Hardware | Live agreement |
|---|---|---|---|---|---|---|
| 2.5 | pending | pending | pending | pending | pending | pending |
| 5 | pending | pending | pending | pending | pending | pending |
| 10 | pending | pending | pending | pending | pending | pending |
| 25 | pending | pending | pending | pending | pending | pending |
| 60 | pending | pending | pending | pending | pending | pending |

## Coordination

Coordinator and original FPGA owner notified of this task and source isolation.
The original FPGA task retains .18/.17 bench ownership. No device has been
opened, configured, or deployed by this task. Build/simulation work proceeds
without hardware; request a specific .18 window only after full design route.
Scanner task asked for saved positive and independent control/holdout locations.

## Current limits

Inherited pilot replay proves host GLRT after a 15-to-2.5 DDC. It contains no
FPGA GLRT and does not qualify any requested rate in this new profile.
No sensitivity, false-positive rate, timing closure, transport headroom, or
live agreement is claimed yet. Proposed resource counts are budgets, not
measured utilization. No production deployment or source promotion is authorized.

## First digital implementation checkpoint

The new `hdl/library/starlink_glrt` contains an independent unity/multirate
exporter and a native-rate 64-symbol exact/control correlator. These blocks have
no PSS dependencies. Coefficient and published pilot-state banks are frozen by
byte hashes. The correlator is one GLRT stage; it does not yet implement the
frequency maximization, autonomous acquisition or final decision.

The first aggregate suite passed 92 tests. Ten additional exporter tests passed
after explicit rejected-input accounting, counter-wrap refusal and clean-flush
coverage were added (39 exporter RTL tests total). The independent correlator
suite has 25 tests across all rates and both edges. The suite distinguishes
engineering fixtures from held-out detector qualification; thresholds are not
yet frozen and no measured false-positive rate is claimed.

An initial 60 MS/s standalone exporter failed placement because replicated
history needed 8448 LUT RAM sites (6000 available). The banked redesign's
`artifacts/ddc-60000000-v3` route used 4122 LUTs, 1093 registers, 24 DSPs and zero
BRAM, with internal setup/hold slack +0.158/+0.053 ns at 100 MHz. All 6626
routable nets routed without errors. Its unplaced boundary ports have 549
TIMING-15 hold warnings, explicitly outside that internal timing gate. This is
not a receiver timing pass. Subsequent accepted-counter/wrap changes require a
fresh route; the v3 result remains tied to the source hashes in its summary.

`NUMERICAL_SPEC.md` in the new HDL library documents the 64-symbol GLRT model,
the host normalization difference, CFO alias interval, resource budget and
native sample-ring admission. Native correlator synthesis is now running;
FPGA DFT/scoring, blind acquisition, CDC/control/DMA, kernel and host integration,
full receiver route and all hardware/live gates remain pending.
