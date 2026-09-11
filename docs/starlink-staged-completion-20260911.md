# Clocked producer completion — DO NOT MERGE

Baseline is clocked admission FW `017202701`, HDL `956dc4a1a`. Its final actual
FFT campaign and 321 tests passed, but routed timing still failed at -3.080 ns.
The worst path ran through input identity/current faults into completion receipt.

## Implementation contract

Reuse the single-use private certificate primitive for a 28-fact completion
record. ACK_DRAIN retains phase, descriptor and relevant bank ownership while
the facts are checked. Forward capture begins only after the forward guard has
retired and the committed product bank is visible; inverse capture begins only
after the real output-publication receipt. Neither a capacity guess nor an idle
reader ACK substitutes for these conditions.

The record captures the existing 19 partitioned current-fault facts, the original
cutover fault predicate, both input strobes being quiet, all three raw output/
status/frame strobes being quiet, and forward identity/position/TLAST validity.
A clean record issues one private completion receipt on the following edge.
The scheduler/cutover consume that receipt on the next edge with registered
quarantine. A coincident new fault may advance private receipt/state, but the
unchanged epoch fault registers prevent a new FFT start/configuration/input or
public output. Reset/quarantine/request withdrawal cancel the pending record.

Actual public publication and final reader ACK/release checks are unchanged.
The older full completion predicate remains as the default-mode implementation
and as an actual-bench comparison at every requested completion snapshot.
The new contract is enabled only by the existing registered/offered/contextual
experimental combination. No production receiver sources or gitlink are promoted.

## Required evidence

The real-FFT bench retains six numerical/backpressure contexts, two stopped-reader
reset cases, seven previous fault cases and six admission-cancellation cases.
Ten new completion-cancellation cases cover faults before capture, before
consumption and before receipt application in both forward and inverse phases;
wrong forward metadata or position; and reset from either clock side with a
pending inverse close. Tests require no later core reuse, publication or reader
release. They are bounded interface tests, not an exhaustive formal/CDC proof.

The isolated certificate tests cover both 22- and 28-bit configurations, including
66/84 zero/X/Z rejection trials, held evidence, one-shot consumption and reset/
quarantine cancellation. Unsafe bypass, refresh, reuse and quarantine mutants
must fail. Parser controls do not count as additional FPGA executions.

V1 actual generated-FFT verification **passes in 87.43 seconds**. The independent
audit matches all **64,512 numerical records** against the pinned prior actual
reference. All retained and ten new cancellation cases pass. The bench observes
74 admission and 59 close receipts, including aborted jobs. Service intervals
are 3659/3659/4927/11727/3659/3659 fast clocks: the normal interval is two clocks
longer than the admission baseline; the qualifying stalled case remains 4927.
Only the deliberately 9000-clock-stalled reader is exempt from the 5215 cap.

The isolated certificate campaign passes **10 tests in 0.08 seconds** for both
widths and their unsafe mutants. V1 synthesis completes in 97.42 seconds.
Before/after sources remain unchanged, with the same real FFT wrapper, device,
diagnostic clocks and implementation recipe. No constraint exception was added.

Frozen inventory SHA256:
`34be78657f1e0a3689042eefa07d16b7cbad07d88fc6b693fc8e9e74114f123c`.
Numerical CSV SHA256:
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
V1 combined regression passes **334 tests in 45.68 seconds**. Source-matched
routing completes in 55.28 seconds but regresses to **-3.637 ns**, TNS
**-1943.578 ns**, 1368 failing setup endpoints. Hold +0.058 ns and pulse +1.830 ns
pass; 8275 nets route with zero errors. Resources are 2718 LUT / 5584 FF /
21 DSP / 15 RAMB18. Fewer endpoints than the baseline do not offset worse WNS
and TNS: V1 is not accepted as an overall timing improvement.

The worst V1 path goes from product metadata through current fault/return
qualification to the kernel ROM enable: 11 logic levels, 8.824 ns data delay
(7.004 ns routing). V2 extends the joiner's existing private-payload mode into
the ROM: output data/metadata and first-bin private metadata may load whenever
the elastic output stage has capacity, including invalid input bubbles. A
stalled valid output still freezes. Output-valid, error handling, ordinal,
expected-next-block and completion updates retain their original full checks.
Default mode retains the original qualified loads. Invalid payload bits are
private and may change; this is not permission to publish an invalid result.

Four standalone ROM tests pass in 0.24 seconds. They compare original frozen
RTL with both candidate modes on every clock: public controls always match;
data/metadata match whenever valid, including stalls. The campaign covers
4096 healthy lookups over eight blocks, input bubbles with changing metadata,
four malformed-input cases and stalled-output flush/recovery. Three unsafe
mutants (ignore stall, publish bubbles, bypass validation) are rejected.
Original RTL and ROM coefficients are independently SHA256-pinned.

V2 actual FFT verification passes in **86.64 seconds**, with the full numerical
CSV and every parsed service/reset/fault/admission/completion result identical
to V1. V2 synthesis completes in **97.08 seconds**. Sources remain unchanged.
V2 frozen inventory SHA256:
`9ef0ccb07b0739a61a0bc5b6559594198c78047b93ade9215f29fff5ac2c31f8`.
V2 combined regression passes **346 tests in 46.17 seconds**. Source-matched
routing completes in **71.59 seconds**, still **failing at -3.134 ns**, TNS
**-1304.699 ns**, **1398 / 13586** failing setup endpoints. Hold +0.070 ns and
pulse +1.830 ns pass; 8376 nets fully route with zero errors. Resources:
2773 LUT / 5594 FF / 21 DSP / 15 RAMB18. Compared with the admission baseline
(-3.080 ns, -1541.860 ns, 1511 endpoints), WNS is slightly worse while TNS and
endpoint count improve. Compared with V1, WNS/TNS improve but endpoint count
rises. This is mixed physical evidence, not timing closure or a release.

The worst V2 path is engine metadata → preflight/current fault logic →
`output_control/phase_reg[2]`: 10 logic levels, 8.793 ns data delay including
7.097 ns routing. Publication-controller sequencing is the next boundary to
inspect. Separate private replay consumption from actual bank publication only
if a fault-edge private advance is demonstrably cancelled before notification
or RELEASE. Actual authorization must still see the current fault, publication
must still observe the bank request transition, and release must still require
the real final-reader ACK. Add boundary tests before another actual/route run;
do not waive timing paths or remove public fault checks.

V2 CDC remains unqualified: 5 critical, 208 warning and 4 informational findings,
with 114/124 unconstrained I/O ports. All vendor handles are terminal. Independent
audit verifies checkpoint/source receipts, all clock pairs, timing summary,
utilization and complete routing. V2 synthesis DCP SHA256:
`85006af21c7e0815ea12714710b40be582757b199a615eb16b8e9c50735926b2`.
V2 routed DCP SHA256:
`298832d0be4428422a6eca70ae6ed36a93fb70aac0efee68a1045b57563f5cc5`.

V1 synthesis DCP SHA256:
`bf0e120781f94ece35e328ba78cbfd0e86f8d4b6e6043dd631694aeb1cfddfc7`.
V1 routed DCP SHA256:
`1140e8f16ea590fe71613514cf96dd4454f18be9894fa52475e9bfa9d4db734e`.

## Release gates are unchanged

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain requirements.
Full receiver route, actual clock placement and board delays, CDC/reset, sustained
capture and actual RX calibration must pass before `.18` reversible canary,
then `.17` PPU Ethernet-only deployment with pinned rollback. Finish the
300-second / 120 ms valid-dwell blind FPGA-versus-host GLRT campaign. No radios,
PPU settings or main branches are changed by this subsystem experiment.
