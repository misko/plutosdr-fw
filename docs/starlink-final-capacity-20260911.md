# Final product-slot capacity isolation — DO NOT MERGE

Branch: `codex/starlink-rx-only-do-not-merge-product-final-capacity`.
Parent FW `967db3daa1f69e9ac17960c33d1533c7afb0cb03`, HDL
`0705316ad41b7f056d6acaae82e28a4c9a4e8a13`.

## Narrow runtime change

The integrated product stage's input READY no longer permits simultaneous
retirement/refill when its retained word is LAST. Nonfinal words retain
continuous pop/refill and first-reference metadata write-through. Publication
authorization, output retirement, fault/reset vetoes, payload and certificates
are unchanged. The actual bank still owns the block until its real reader
returns ownership. An empty private slot becomes available on the clock after
LAST retirement, not on that retirement edge.

This targets the measured parent path from final-publication authorization back
through product-stage READY, arithmetic/joiner readiness and protocol faults.
It does not insert the first-word pause that overflowed the actual FFT in the
parent's rejected V1. Only one assignment changes in one of 21 runtime modules;
the other 20 and the complete top-level wiring remain byte-identical.

## Verification

Focused preflight: 26 tests pass in 3.25 s. Full regression: 606 tests pass in
80.43 s. These overlap; do not add them together. Four unsafe capacity mutants
are rejected. Directed cases cover nonfinal refill, a queued next word during
held LAST, blocked/allowed/unknown readiness, no unpublished-word loss, next-edge
reopening, current abort, sticky quarantine and reset recovery.

The actual FFT bench adds monitors, not new cases or extended deadlines. During
held LAST, upstream capacity must remain zero and a healthy producer must be
quiet. A subsequent forward job may start only with an empty private slot and
actual bank ownership returned. All inherited numerical, ownership, certificate,
ACK, publication and fault/reset cases remain intact.

Auxiliary actual FFT passes in 108.49 s: six original ACK cases, 12 forward
receipt cases and 12 product-stage cases, each with fresh recovery. The capacity
witness checks 166 final-slot cycles and 54 forward starts. Original product
witness: 25055 captures, 25036 retirements, 25167 checked slots, 51 reference
updates and 131 held-slot checks. Cancelled private words explain captures minus
retirements; these counts are not RF detections.

Main actual FFT passes in 212.37 s. All 64512 indexed results and the complete
CSV SHA256 match the parent:
`210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Service remains 3662/3662/4929/11729/3662/3662 clocks. The intentional 9000-clock
reader stall remains excluded from the unchanged 5215-clock coarse-service
gate. Main capacity witness: 98 final-slot cycles and 107 forward starts.
All inherited product/receipt counts match the parent.

Ten new evidence-auditor tests pass; seven overlapping archive-writer tests also
pass in the same 0.76 s invocation. Total distinct regression/evidence tests:
616. Missing/duplicate/short/altered final-capacity receipts and removal of the
compiled campaign's audit cannot silently authorize routing. Both actual runs
must use the same prepared source inventory as synthesis, with fresh audits.

Synthesis completes in 104.87 s with unchanged source receipts.
Routing completes in 43.25 s with 8469 fully routed nets and zero routing
errors. **Setup still fails: -3.252 ns WNS, -2279.503 ns TNS, 1330 of 14136
failing endpoints.** Immediate parent: -4.115 / -3456.457 / 2297. This recovers
0.863 ns of worst slack and removes 967 failing endpoints, but remains worse
than the pre-product-stage forward-receipt reference (-1.567 / -497.191 / 681).
It is not timing closure and must not be promoted or deployed.

Resources: 2804 LUTs, 5780 flip-flops, 21 DSPs, 15 RAMB18s and no RAMB36s.
Hold +0.070 ns, pulse width +1.830 ns, neither with failures. The diagnostic
still has 114 unconstrained inputs and 124 outputs. Constraints and routing
recipe are unchanged; no clock relaxation or timing exception was introduced.

Worst path: `cutover/fault_reasons_reg[7]/C` to
`admission_gate/snapshot_good_reg[6]/R`, 12 logic levels, 8.358 ns data delay,
6.352 ns routing (76.0%). It crosses registered-quarantine qualification,
input duplicate-start/current-fault logic, final readiness, kernel READY and
the admission snapshot reset. The next reported path reaches arithmetic DSP
clock enable through the same shared control network. The capacity edit does
not fully isolate that network; behavioral nonfinal/final exclusion alone did
not produce the intended short physical boundary.

## Next bounded step

Do not add further features or remove TX logic to address this path. Investigate
a block-scoped producer-capacity contract: admit the block only after reserving
its actual destination, then keep local nonfinal streaming capacity separate
from final-publication authorization. Any capacity credit must come from real
bank ownership, survive only its valid epoch and expire on actual completion or
reset. Public writes/publication/admission must retain immediate current-fault
vetoes; simply registering a shared fault or trusting stale READY is not safe.

First prove the invariant against the actual mailbox for every nonfinal word,
held LAST, unexpected capacity loss and reset/fault edges. Then integrate and
run both actual-FFT campaigns and the unchanged service gate before routing.
Retain the forward-receipt reference as the better physical baseline. No such
new credit architecture is implemented in this checkpoint.

## Scope and evidence

Prepared inventory:
`408204bad0b135494839b37ce242f2cc720e9e918e293aaedcdc0d6a0105a0f6`.
RAM artifact root: `/dev/shm/starlink-final-capacity.vMIiHM`.
Synthesis DCP:
`bc085a9db18734818483d396c59b1d979767556049c62fffa37914e4c8abc94d`.
Routed DCP:
`43a0aba1274f5af69ec5e2adf86c0beb4bf181430009ffa37a32d9fe8cd8cb5a`.
Parent inventory:
`b84f82584aa9adfd144efb9a1e82ca1731af4cb00425d82e9cb491e577969e84`.
Historical fixtures are an explicit dependency on the already-pushed parent
evidence archive, SHA256
`3fba1792846ac692727c2896e6637dad85571d999aeb2e905b39de04804672e5`.

Native 60 MS/s fine search and the independent 2.5 MS/s CI16 IIO inspection
stream remain untouched. This isolated 100/175 MHz diagnostic is not full
receiver/board timing, continuous 750 Hz throughput, native RX calibration or
RF accuracy signoff. No radio, PPU/main or primary production HDL changes.
Full receiver timing/CDC/reset, sustained Ethernet/IIO and real RX calibration
remain gates before reversible `.18` canary and `.17` PPU Ethernet-only rollout.
Keep pinned rollback and require 300-second scans, 120 ms valid dwells and blind
host GLRT comparison. `.17` remains outdoor LNB RX-only, not a bench transmitter.
