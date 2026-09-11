# Split product capacity interface — DO NOT MERGE

Branch: `codex/starlink-rx-only-do-not-merge-split-product-capacity` (FW and HDL).
Parent FW `d499446693de5f26fc16bd6b0ac183ae156b74e7`, HDL
`44cf696a9d78701246e2d309b1cd1befd3eea216`.

## Implementation and caller contract

The actual FFT's product stage now takes separate physical nonfinal capacity
and publication-qualified output readiness. Capacity is the known-true actual
product-bank READY, fenced by known-false `fast_fault`. No credit is predicted,
no fault is delayed, and no new state is introduced. The mailbox's raw READY
already expresses writer ownership versus the real reader's acknowledgement.

The specialized stage changes only its module name, adds `refill_capacity`, and
uses that input in the nonfinal simultaneous-refill term. All payload/metadata,
identity, fault, reset, full-slot and output-retirement logic remains literal.
The original stage remains available as the independent reference. The compiled
inventory replaces it with the specialized stage: still 21 runtime modules.
Top-level changes are exactly the stage type and the new capacity connection.

The required caller contract is that a live nonfinal slot's capacity equals
its actual output readiness. The unchanged top-level final-readiness expression
satisfies this for the actual mailbox; only LAST adds the publication condition.
LAST cannot refill on its retirement edge. The stage is not a general-purpose
elastic buffer for arbitrary contradictory capacity/retirement inputs.

This is an explicit physical interface split, not the block-credit controller
suggested as a possible next design in the parent report. Existing actual bank
ownership supplies the needed capacity directly, so no additional controller
state is justified before measuring this simpler alternative.

## Verification

The component comparison instantiates both real stage implementations with
their actual caller expressions. It checks every output and held payload before
and after every edge through a 512-word continuous block, held LAST with queued
next offer, readiness stalls, all 32 nonfinal/final × four-state capacity ×
four-state authorization combinations, sticky faults and reset recovery.
Four mutants must fail: final refill, premature final retirement, ignoring
bank capacity, and ignoring abort. Exact source inverses prove the runtime
change and preserve all other compiled modules and top-level wiring.

Initial preflight found a Python test import error (16 pass, one fails), not an
RTL failure. Correcting the package-qualified import yields 17/17 passing in
0.18 s. Both initial and corrected results are retained.

The actual FFT bench adds a clock-by-clock comparison of producer READY against
the prior expression and of nonfinal capacity against actual retirement. It
retains all existing numerical/ownership/fault/reset cases and deadlines. Route
requires both source-matched actual campaigns and independently re-audited
split-capacity receipts; deleting an audit field cannot bypass the requirement.

Full regression: **622 tests pass in 81.70 s**. The focused tests overlap this
suite and are not additional counts.

Auxiliary actual FFT: **107.99 s**, all six original ACK cases, 12 forward
receipt cases and 12 product-stage fault/reset cases pass with fresh recovery.
Split witness: **243356 checked clocks / 25001 nonfinal transfers**, exact
acceptance and retirement. Inherited product/receipt/final-capacity counts match
the parent. Synthesis completes in **99.90 s**, unchanged source receipts.

Main actual FFT: **204.28 s**, all **64512 indexed numerical records** and the
complete CSV match the parent. Service remains
**3662/3662/4929/11729/3662/3662 clocks**. The intentional 9000-clock reader
stall is excluded from the unchanged 5215-clock coarse-service gate. The actual
main split witness checks **500595 clocks / 50761 nonfinal transfers** with
exact producer capacity and current retirement behavior. All inherited receipt,
ownership and product-stage counts remain identical.

Nine new split-evidence tests pass; seven overlapping archive tests also pass
in that 0.99 s invocation. **631 distinct regression/evidence tests** pass.
The directed component comparison checks 1374 pre/post-edge observations.

Routing completes in **46.99 s**. **Setup still fails: -1.938 ns WNS,
-541.200 ns TNS, 981 of 14152 failing endpoints**. Parent:
-3.252 / -2279.503 / 1330. The interface split improves worst slack by
1.314 ns and removes 349 failing endpoints. It remains worse than the older
forward-receipt reference (-1.567 / -497.191 / 681); it is not a new overall
best timing result and is not deployment-eligible.

All 8450 nets route without errors. Resources: 2777 LUTs, 5788 flip-flops,
21 DSPs, 15 RAMB18s and no RAMB36s. Although no RTL state was added, synthesis
and implementation produce eight more flip-flops than the parent. Hold
+0.072 ns and pulse width +1.830 ns have no failures. The diagnostic retains
114 unconstrained inputs and 124 outputs; no constraints or exceptions changed.

Worst path now starts at `output_control/phase_reg[0]/C` and ends at
`owners[1].result_guard/active_private_reg/D`. It crosses the replay/live output
metadata selection, 37-bit output-bank metadata equality, current framing-fault
qualification and inverse result-guard control. It has 11 logic levels,
7.645 ns data delay and 5.687 ns routing (74.4%). The next path reaches the
inverse commit pulse through the same network. Moving the worst endpoint is
not proof that every product-side path now meets timing.

## Next bounded boundary

Investigate the output descriptor/identity boundary before adding features.
Separate the stable private output descriptor from replay/publication phase
selection, and determine whether identity can be certified before the wide
metadata predicate reaches inverse completion control. Retain actual final
framing, reader ownership, current corruption/fault vetoes, epoch cancellation
and release ordering. Merely replacing the metadata with an assumed constant
or delaying a current fault would weaken the contract and is not a fix.

First test the descriptor lifetime against the original mailbox, including
first/nonfinal/final metadata changes, replay-boundary corruption, unread output,
real ACK and both reset sides. Then integrate, compare all actual FFT values and
service intervals, and route with unchanged clocks. Preserve the better older
physical reference. This output-boundary change is not implemented here.

## Scope and evidence

Prepared inventory:
`d60c44681da7625f756b05315b626577a165eb29da9761d528e126508c9155f4`.
RAM artifact root: `/dev/shm/starlink-split-capacity.URCQhd`.
Synthesis DCP:
`1d104ec7d70759ea2657c91269f7e2babc64abc03c8535db6b8b40e70a805e8d`.
Routed DCP:
`0d9c2db85313c132ea50b58056aa0bc89d9d9eda568acb2d0cd5536bc5b244e5`.
Numerical CSV:
`210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Parent inventory:
`408204bad0b135494839b37ce242f2cc720e9e918e293aaedcdc0d6a0105a0f6`.
Historical evidence dependency: parent archive SHA256
`2d6cbccd814457936228571176ccbac0619af9324c032ab542e42a4f2b4ce847`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
untouched. No radios, PPU/main or primary production HDL changes. The isolated
100/175 MHz diagnostic does not establish full receiver/board timing, continuous
750 Hz throughput, native calibration, Ethernet performance or RF accuracy.
Those remain gates before reversible `.18` canary and `.17` PPU Ethernet-only
deployment with pinned rollback, then 300-second scans with 120 ms valid dwells
and blind host GLRT. `.17` remains outdoor LNB RX-only, never a bench transmitter.
