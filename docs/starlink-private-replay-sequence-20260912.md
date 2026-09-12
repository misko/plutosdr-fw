# Private replay sequence offer — experimental, DO NOT MERGE

This candidate separates private kernel sequence bookkeeping from the current
forward-bank validation path. It does not change the FFT, its coefficients,
public stream eligibility, bank ownership, current fault diagnostics or either
actual publication veto. Native 60 MS/s fine search and the independent 2.5 MS/s
IIO inspection stream remain full receiver release requirements.

## Baseline and exact changes

The runtime baseline is the output-retirement candidate, not the newer handoff
factoring experiment (which regressed aggregate timing). All 39 baseline runtime
modules remain byte-identical. Two derived modules are added, for 41 total:

1. The forward bank exports `private_replay_valid` from reset, registered REPLAY
   state, registered data-valid, sticky local fault and abort. Existing bank
   state, RAM, outputs, current full fault and public valid are unchanged.
2. The top connects that offer only to the kernel's existing private-sequence
   input. Public input-valid still comes from the original full current check.
   Both original final-publication vetoes still consume the full current fault.

No new logical state is introduced. A newly rejected replay may advance hidden
kernel sequence state once, but it cannot publish a coefficient, public
completion or bank request. Local sticky fault and quarantine take effect on
that edge; no further private offer or reuse is allowed before common reset.

## Verification

- Exact forward/reverse source transforms permit only the additive port,
  combinational offer, top rename/bank substitution and private-input wiring.
- All 21 existing bank scenarios compare every existing control and state
  against the unchanged parent. 1,024 four-state replay-control combinations
  verify private-only offers imply current faults, stop on the next edge and
  recover 4,096 fresh words. No old bank state difference is permitted.
- Actual FFT healthy simulation passes 64,512 numerical words and 4,178 service
  clocks, unchanged from the parent. The independent kernel reference receives
  original public/private eligibility and compares public controls and valid
  coefficients before/after each edge. Healthy: 177,090 comparisons, 9,216 takes,
  no private-only takes or hidden-state differences.
- Eleven new actual cases exercise first/middle/final replay, unexpected
  capture/seal, unknown reserve-valid and both raw resets after private final
  bookkeeping. Every case requires checked publication vetoes, no ownership
  change, quarantine and fresh 512-word/one-release recovery.
- The final focused campaign also exercises all five inherited forced-ready
  branches: reset at two replay positions on both reset inputs, and an elastic
  stall. It passes with 462,472 reference comparisons, 21,496 private takes,
  11 private-only takes, five private-only finals and 2,045 quarantined private
  state differences. This focused run is not the complete inherited campaign.

Two test-harness failures are retained:

1. Initial smoke required the slow-domain fault flag before its two-register
   synchronizer could report it. Version 2 preserves every immediate local
   quarantine/ownership check during 12 fast clocks, then requires the slow flag.
   Actual traces show local fault/quarantine = 1 while slow fault = 0.
2. Initial full auxiliary run applied inherited forced-ready stimulus only to
   the DUT, not the added reference kernel. Version 3 mirrors exactly two
   force sites and three release sites onto the reference's matching input-ready
   net. Strict public comparison remains enabled; no RTL or fault checks change.
   The focused run re-executes every affected branch before the full campaign.

Final regression: 2,107 passing tests. The complete actual campaign passes all
82 cases (71 inherited plus 11 new) in 316.793 s. Its independent reference
makes 1,700,310 comparisons and observes 75,149 private takes, 12 private-only
takes, five private-only finals and 2,272 quarantined state differences. The
extra private-only take is exercised by an inherited fault case. Current bank
publication/ownership checks and all inherited witnesses pass.

## Source pins

- Main inventory: `7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4`.
- Focused version 3: `45e048addd87f6ef2ea93657555f801b74cac7f2f82a028994391769afba59dd`.
- Full auxiliary version 3: `2269c44696bd2c2816e78f15233a7484b846671eb92aad206b53b080747a8b87`.
- Synthesis DCP: `18e77d1b192bec57111cdfebb1110bfaebfd2f87f259246f812ff065fcc53e69`.
- Numeric CSV: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

## Routed result — still not timing closed

The unchanged 100/175 MHz OOC route completes in 50.834 s with all 8,559 nets
routed and no routing errors. It does not close timing:

| Metric | Output-retirement parent | Private replay |
|---|---:|---:|
| Overall WNS / TNS | -1.152 / -343.090 ns | -1.182 / -349.709 ns |
| Failing setup endpoints | 867 / 14,505 | 930 / 14,496 |
| Same-domain 175 MHz WNS | -1.095 ns | -0.970 ns |
| LUT / FF | 2,689 / 5,912 | 2,756 / 5,908 |
| Kernel next-start CE | -0.476 ns | -0.364 ns |
| Kernel index / history | +1.744 / -0.169 ns | +3.061 / +0.375 ns |
| Product / output publication | -1.095 / -0.831 ns | -0.970 / -0.618 ns |

The kernel history endpoint now passes, but next-start CE still fails from a
different source: product-bank request/availability, five LUT levels, 5.825 ns,
81.529% routing. Do not call that endpoint closed merely because its original
capture-metadata dependency was separated.

The worst internal path now starts at product-bank write-position bit 4,
passes through its current framing fault and shared fault logic, and returns
to the same bank's publication request: seven logic levels (one CARRY4 and
six LUT6), 6.631 ns, 70.459% routing. The bank already checks framing locally
before publishing. Next inspect whether this repeated self-fault dependency
can be factored at the actual publication boundary without removing its local
framing check, other fault sources, diagnostics, quarantine or recovery.
Require source-matched actual publication equivalence and aggregate benefit;
this candidate is retained as a tested alternative, not a receiver promotion.

Descriptor CE/data +1.422/+3.013 ns, product occupancy/identity +1.258/+0.793 ns,
output occupancy +0.898 ns. All actual physical request endpoints are included
(one per bank in this checkpoint). RAMB18/DSP remain 16/21. Hold +0.050 ns,
pulse +1.830 ns, zero loops. Nine CDC-3 / 208 CDC-15 / no CDC-10; scalar fault
directly feeds its synchronizer, and reset-release has a physical replica.
114 inputs / 124 outputs remain unqualified. Overall worst is held metadata
crossing to the slow domain, not a qualified asynchronous timing exception.
The routed DCP SHA is `4de735e3fbfb806de94fc6cd3a90d3e402c9ad49777daea07684b01e2564b233`.

## Full receiver/deployment gates

The unchanged 100/175 MHz OOC route must measure all actual kernel block-start
CEs, index/history registers and publication replicas. The parent block-start
CE worst is -0.476 ns and history -0.169 ns. A missing source-specific path
does not prove closure: measure the full destination endpoint from all sources.

This is not full receiver timing, 60 MS/s RX calibration or continuous paired
reception. The existing full receiver uses 100/200 MHz, including a 200 MHz
IDELAY reference. Earlier lower-clock full-pipeline trials failed throughput;
they cannot be bypassed with this short numerical run. No board clocks,
exceptions, PPU or radios are changed by this experiment. Preserve the primary
HDL gitlink. Deployment remains `.18` canary, then Ethernet-only `.17`, through
pinned reversible PPU, after complete receiver and live IIO/RF qualification.
`.14`, `.20` and `.21` remain excluded.
