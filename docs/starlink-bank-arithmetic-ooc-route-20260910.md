# Arithmetic bank diagnostic route: timing FAIL

One authorized route completed, but **175 MHz setup timing fails**. Original
handle 42281 exited 0 after 58.32 s, with one exact terminal marker and all
6,762 routable nets fully routed (9,005 logical nets; zero routing errors).
Tool completion is not timing closure or receiver qualification. No retry,
exception, source edit, or further physical run occurred.

Original owner: `/tmp/starlink-arithmetic-route-v1.VNX5gK`, output `route/`.
Started at 2026-09-10 10:14:03.832 UTC; original Vivado log records exit at
10:15:01 UTC. `collected-after-terminal.utc` is the later collection time,
not an invented process exit time. The original `/usr/bin/time` receipt records
the command, elapsed time and exit 0. Log/journal arguments precede Tcl arguments.

## Exact input and resulting checkpoint

Input synthesis evidence was already pinned at FW
`e7142938e097cfeb22c7ce38f409023e3fc66739`, with HDL
`5b68bb8b488a886c3861537eaf9643ec940003e0`. Inputs remained byte-identical:

- Synthesis DCP: `de5b7ca6849c8111ccfce29ca39bbf8899276c0dea309abb576e70546daf06bf`.
- Unchanged route Tcl: `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
- Routed DCP: `e8a6336eb4079d8d27ac9596cd6fcb7322da656d0f8f04d6ac67e619ed5a7413`.

The route used the original open-checkpoint / opt / place / phys_opt / route
sequence, Vivado 2022.2, SuSE vendor libraries, two threads, and inherited
100/175 MHz constraints. `inputs-before.sha256` equals `inputs-after.sha256`.
The script's copied `route/probe.tcl` has the same reviewed digest.

## Final reported timing

| Path group | Setup worst slack, ns | Setup failing endpoints | Hold worst slack, ns |
|---|---:|---:|---:|
| Global | −1.341 | 497 | +0.038 |
| island_175 → island_175 | −1.341 | 379 | +0.038 |
| source_100 → source_100 | +2.454 | 0 | +0.138 |
| source_100 → island_175 | −0.629 | 40 | +0.122 |
| island_175 → source_100 | −1.222 | 78 | +0.116 |
| Async-default recovery / removal | +0.292 | 0 | +0.621 |

Global setup TNS is −386.804 ns across 10,509 endpoints; island same-clock TNS
is −304.384 ns. Cross-clock TNS is −7.235 and −75.186 ns respectively. All
reported hold groups have zero failing endpoints. Pulse-width worst slack is
+1.830 ns with zero failing endpoints. These are the unchanged-constraint
diagnostic results, not CDC or external-interface signoff.

The worst island path is
`input_guard/expected_position_reg[1]/C` → `input_guard/descriptor_reg[2]/CE`.
Data delay is 6.766 ns: 1.863 ns logic plus 4.903 ns routing, six logic levels
(one CARRY4, two LUT4, one LUT5, two LUT6). The path traverses metadata validity,
held-phase/preflight logic and descriptor job-start enable. The full twenty-path
same-domain max/min reports and global/cross-clock/recovery/removal/IO reports
are preserved without filtering. No claim follows that every product path closes.

## Routed resources and remaining qualification gaps

The routed island uses 1,994 LUTs (1,806 logic + 188 SRL), 4,557 FFs,
1,082 slices, 21 DSP48E1 and 15 RAMB18E1 (7.5 BRAM tiles). Product wrapper/core
is 54 LUT / 357 FF / 4 DSP; this is hierarchy attribution, not measured receiver
savings or an independently queried DSP-register mapping proof.

The input clocks remain source_100=10.000 ns and island_175=5.714 ns as rounded
by Vivado. There are 114 input ports without input delays, 124 output ports
without output delays, zero unconstrained internal endpoints, and both clock
ports lack HD.CLK_SRC. OOC port routing also reports missing HD.PARTPIN_LOCS.
CDC remains six CDC-3 informational entries plus 139 CDC-15 warnings. No waiver
was introduced. The inherited XDC contains only the original clock constraints.

No full receiver, radio, native-fine/pilot concurrent integration, .18/.17
deployment, or timing-accuracy qualification is implied. Original actual-core
numerical evidence is unchanged, including its separately documented automation
FAIL / post-hoc functional assessment distinction. The full 15/30/60 source,
2.5 MS/s pilot and eventual eight-target / 120 ms / 300 s objective remains open.
