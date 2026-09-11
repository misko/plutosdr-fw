# Distributed same-edge sticky fault — DO NOT MERGE

The parent route's slowest same-clock path ran from the actual FFT's flushing
register through input READY and fault accounting to the single fast_fault
register. This candidate replaces that one scalar sticky capture with nineteen
independently captured cause groups at the SAME register boundary. Their OR
is the effective sticky fault. It adds no fault-response cycle.

## Exact functional boundary

For known offered/contextual configuration and known retained-reservation
semantics, the existing admission_reject bits already partition the scalar
external, guard, mailbox and result faults. The six preflight bits select the
original preparation fault outside a known active epoch, matching the current
scalar context selection. Other/unknown configurations put the original scalar
fault in bit zero, preserving the unrestricted fallback.

Each cause uses a procedural conditional: clear on the original synchronous
reset, otherwise set only if that cause is true, otherwise hold. A vector OR
update would incorrectly turn unknown causes into unknown stored state, unlike
the original scalar conditional. Effective sticky output has exactly the same
reset/capture/persistence behavior; all existing immediate publication vetoes
and diagnostics still use their original current-fault expressions.

Only the top changes at runtime, plus an additive bench witness. There are
still 22 runtime modules. No arithmetic, sample-rate, interface, clock, timing
exception, synthesis helper or Tcl changes. Existing source inverses explicitly
remove this delta before checking their historical transformations.

## Verification and physical gates

The source-extracted scalar reference and current capture block pass 313297
clocked four-state checks over configuration, reset, preflight selection,
individual/overlapping causes and persistence. Mutants dropping reset, a first
or last cause, sticky behavior, known-context selection or fallback fail.
The exact source inverse fixes the mapping to the original fault predicates.
These finite checks are not a full formal proof of every integrated state.

Both actual generated-FFT campaigns must compare the current source-vector
reduction with the original scalar and compare the new register OR with a
clocked original scalar reference. They record fault, reset and per-cause
coverage while retaining every existing numerical, public handshake, forced
guard-summary, late-fault and recovery test. The forward-final handshake witness
remains mandatory too. Missing, duplicate, changed or vacuous markers block
routing.

Route the frozen source-matched pair with the unchanged recipe. Query all fault
capture registers, including replicas, from the actual FFT flushing register;
also query worst same-island fanout from the capture registers. Compare these
with the parent checkpoint and full timing reports, not only the targeted path.
The effective fault is now a combination of sticky registers: its path to the
slow-domain synchronizer needs explicit CDC/structure review. Boolean equivalence
and monotonic sticky semantics alone do not constitute physical signoff.

## Measured outcome — reject this topology

1017 regression tests plus ten evidence-gate tests pass (1027 distinct).
Main/auxiliary actual FFT runs preserve all 64512 numerical records/CSV and
service clocks 3663/3663/4929/11729/3663/3663. Sticky witnesses cover 503565
and 437626 clocks, 6957/2750 fault-present clocks and 2922/2260 reset clocks.
The combined observed-cause mask is 0x66fff: groups 12, 15 and 16 were not
asserted by the actual campaign. They are covered by the finite source/capture
contract, not by a claimed full integrated fault-injection sweep. Existing
forward-final witnesses retain 98/84 accepts and 941189 exact observations.

| Metric | Scalar parent | Distributed capture |
| --- | ---: | ---: |
| Global WNS (ns) | -1.331 | -2.514 |
| Same-island WNS (ns) | -1.189 | -2.120 |
| TNS (ns) | -277.204 | -678.141 |
| Setup failures | 526 | 1184 |
| LUT / FF | 2732 / 5798 | 2775 / 5809 |
| FFT flushing → fault capture (ns) | -1.189 | +0.624 |
| Worst capture-register → island (ns) | -0.976 | -1.999 |

The intended input path improves, but its OR moves onto downstream control
paths. The global worst is cause 18 to the slow-domain first synchronizer
stage; CDC now reports one critical CDC-10 (combinational logic before that
synchronizer), eight CDC-3 and 208 CDC-15. No waiver is applied. Same-island
worst is inverse guard fault reasons through input/control qualification to
the forward guard input counter enable: nine levels, 7.581 ns data delay,
76.7% routing. All 8475 nets route; hold +0.058 and pulse +1.830 ns pass.
DSP/RAMB18 remain 21/15. Reset first-stage fanout and registered-purge checks
pass but do not cover or excuse the new fault-crossing regression.

The matched path inventory includes all 19 cause registers and one replica.
Two initial read-only probes failed closed on their cell selection: wildcard
syntax under regexp filtering, then the generated hierarchy prefix. Both
scripts/logs are preserved. Corrected, matched probes query the actual parent
and candidate registers; no absent-object result is treated as a removed path.
Runtime and route sources were unchanged throughout.

Do not promote. Preserve the scalar parent and this rejected evidence.
Next keep the original single fast_fault register and its direct registered
CDC source, but feed that register from the already checked flatter cause
expression. This tests logic absorption BEFORE the existing register without
putting a reduction tree after it or adding fault-response latency. Reuse the
four-state/source witnesses and require actual fault/reset/publication agreement,
all numerical/service gates, direct registered fault CDC structure, then a new
matched route. Whether it improves physical timing remains unproven.

## Deployment

Native 60 MS/s fine search and the independent 2.5 MS/s CI16 IIO stream remain
required. Full receiver timing/CDC/real board clocks, actual 60 MS/s calibration,
continuous RX, Ethernet/IIO throughput, blind GLRT, 120 ms valid dwells and
300 s scans remain gates. Then qualify pinned PPU/rollback on .18 before .17
Ethernet-only deployment. No radios, PPU/main, primary HDL gitlink or TX are
changed here; .20/.21 remain excluded.

Raw evidence: /dev/shm/starlink-sticky-fault.4qIKHja5.
Prepared SHA: 9cd61fa49b0dc1313c1c6c03679a5cf0fd757cb6ac76ad8c2b8325fcf5e40f50.
