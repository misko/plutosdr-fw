# L1/R1B1O1/175 diagnostic route: timing FAIL

The one authorized route completed, but timing constraints are **not met**.
Original handle 30536 exited 0; the owner and Vivado process both completed once,
with one exact diagnostic marker and unchanged input checkpoint/script hashes.
Tool completion is not timing qualification. No retry or subsequent optimization
was performed.

## Source and execution

Runtime cohort remains the actual-tested HDL `62da6a39edb8e40e08d41cbb13ba04af7584842d`;
physical preparation is FW `38dfe9d80c33d841d75ebc2ffb46de09eb03b37b` /
HDL `67a1692e3b09f3aa7166fb8f83b1cf787b363f78`.
Preparation/history evidence is committed at FW `ee5048e7c`, and complete synthesis
evidence at `09db6bd36b0e34b13b8cf2721d80be7c266ffec7`.

The synthesis report is a synthesis-time snapshot. The parent subsequently
authorized this one unchanged diagnostic route. Launch was paused during a
separate storage incident and resumed only after the parent's storage check.
No route was running during that pause and no attempt was discarded.

Owner, route output and TMPDIR are on the recovered filesystem, not `/tmp`:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/local-admission-route-v1.EzXzzuNB`.
Original Vivado PID 648733; start 2026-09-10T12:48:00.560954Z,
end 12:49:15.078927Z, elapsed 74.518 seconds.
The complete argument vector/environment is recorded in `before.json`; the
original exit, post-input integrity and all 15 products are in `terminal.json`.

Vivado 2022.2, xc7z010clg400-1, SuSE library path and two threads remain unchanged.
The exact route script performs `opt_design`, `place_design`, `phys_opt_design`,
then `route_design`; there was no extra optimization or clock/constraint edit.
Inherited constraints contain only the original 10.000 ns source clock and
5.714 ns island clock, with no false paths, multicycle paths or clock groups.

Input synthesis DCP:
`a6a8e404b90924bb538a0da2ae7be7fc9ebc9e0c323b8f1a17661b4550648242`.
Unchanged route Tcl:
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
Both match before and after. Routed DCP:
`8a20a37373e03b12f8546dad6762ac879a02b1eb94ed815fce4790644803b3d7`.

## Reported timing and area

| Path group | WNS ns | TNS ns | Setup failures / endpoints | WHS ns | Hold failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Global | -1.549 | -389.428 | 541 / 10,489 | +0.058 | 0 |
| Island 175 → 175 | -1.549 | -305.523 | 413 / 9,822 | +0.058 | 0 |
| Source 100 → 100 | +1.281 | 0 | 0 / 257 | +0.100 | 0 |
| Source 100 → island 175 | -0.652 | -8.873 | 50 / 67 | +0.128 | 0 |
| Island 175 → source 100 | -1.241 | -75.032 | 78 / 78 | +0.118 | 0 |
| Async reset recovery/removal | +0.673 | 0 | 0 / 265 | +0.711 | 0 |

All groups have zero total hold violation. Pulse-width worst slack is +1.830 ns,
with zero failing endpoints out of 4,905. The 100 MHz maximum path is
`slow_reset_slow_reg[1]/C` → `output_bank/metadata_out_hold_reg[38]/CE`.

Compared with the previous arithmetic-only route (same recipe, L0), global WNS
is **0.208 ns worse** (-1.341 → -1.549), setup failures increase 497 → 541,
and TNS changes -386.804 → -389.428 ns. This experiment does not establish a
timing improvement or a closed clock. One placement per source is not a
statistical place-and-route comparison.

Routed resources: 1,960 LUT (1,772 logic + 188 SRL), 4,551 FF, 1,087 slices,
21 DSP48E1 and 15 RAMB18 (7.5 tiles). The earlier arithmetic route had
1,994 LUT / 4,557 FF / 1,082 slices with the same DSP/BRAM counts.
Fewer LUT/FF here did not improve timing or occupied-slice count; cross-hierarchy
optimization and placement prevent attributing those differences to a simple
per-module savings. Synthesis was 1,945 LUT / 4,547 FF, just one LUT above L0.
All 6,676 routable nets are fully routed, with zero routing-error nets.
Original outer log contains no ERROR or CRITICAL WARNING lines.

## Actual limiting control paths

Worst path, -1.549 ns:
`registered_scheduling.held_phase_reg_replica_1/C` →
`result_guard/fault_reasons_reg[0]/D`.
Data delay is 6.925 ns: 1.477 ns logic + 5.448 ns route, eight LUT levels.
The reported path crosses product-bank identity leaf logic, input-guard balanced
identity/metadata logic and current input-fault logic into result-fault storage.
This is not the previous worst `expected_position` → input-guard descriptor CE
path. Its absence as the worst path is not proof that every descriptor path is
closed.

Second reported path, -1.510 ns:
`result_guard/descriptor_reg[61]/C` →
`registered_scheduling.admission_receipt_reg/D`.
Data delay is 7.127 ns: 1.324 ns logic + 5.803 ns route, seven LUT levels.
It crosses output-bank metadata comparison/current fault logic into admission.
The third reported path is -1.381 ns from the product exponent register to the
kernel-ROM block-start CE. Full maximum/minimum reports and exact netlist arcs
are retained; no new netlist observation or physical run was used to collect them.

## Qualification limits

Check-timing still reports 114 input and 124 output ports missing delay
constraints; zero unconstrained internal endpoints, unclocked pins or loops.
CDC reports six Info synchronizers and 139 Warning clock-enable-controlled
crossings, with no exceptions. Both OOC clock ports lack HD.CLK_SRC, and external
ports lack HD.PARTPIN_LOCS; external paths/clock placement remain unqualified.
Positive same-domain hold/reset numbers do not certify CDC, board I/O or the
complete receiver. No external-port timing pass is claimed.

The prior exact actual-core numerics, fault tests and settled pre-NBA 155-bit guard
comparisons remain separate functional evidence. This route does not replay them,
alter their successful/failed history, establish scorer RTL accuracy, or qualify
continuous-source operation, native fine/pilot concurrency, RF accuracy or release.
No D/S/CDC union, runtime promotion, radio or PPU work was performed.
