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

Final regression: 2,107 passing tests. The complete actual campaign is required
to retain the 71 inherited cases plus all 11 new cases before routing.

## Source pins

- Main inventory: `7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4`.
- Focused version 3: `45e048addd87f6ef2ea93657555f801b74cac7f2f82a028994391769afba59dd`.
- Full auxiliary version 3: `2269c44696bd2c2816e78f15233a7484b846671eb92aad206b53b080747a8b87`.
- Synthesis DCP: `18e77d1b192bec57111cdfebb1110bfaebfd2f87f259246f812ff065fcc53e69`.
- Numeric CSV: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

## Physical/deployment gates

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
