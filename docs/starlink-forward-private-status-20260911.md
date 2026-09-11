# Registered private forward-bank status — DO NOT MERGE

This experiment retains the actual FFT and buffers. Native 60 MS/s fine search
and independent 2.5 MS/s inspection remain required; their receiver sources are
unchanged. This isolated subsystem is not a deployed receiver.

## Interface change

The derived bank exposes its existing sticky `fault_q` as `private_fault`.
The original current `fault` signal, RAM/seal/replay rejection, state and reset
remain unchanged. Thirty-one parent runtime modules remain byte-identical.

Private bank readiness and the product-bank fault aggregate use registered
status. Registered quarantine also consumes this status directly. Product and
output publication retain explicit current-bank-fault vetoes. The scalar global
fault register and its synchronizer are not replaced with a distributed OR.

This is not cycle-equivalent controller fault timing: an independent bank fault
can reach the guard one edge later and global fault by the third rising edge
from the original event. A same-edge private completion can occur before the
bank sticky register updates. Tests must prove no ownership publication then,
and no subsequent job/completion reuse once that register is set. A previously
published good block can remain visible during fault CDC; cancellation tests
hold the reader and do not claim retroactive withdrawal of earlier reads.

## Completed functional checks

- 1,497 distinct regression tests pass, including 46 new component/witness and
  39 new route-admission tests. The separate component rerun is a subset.
- Twenty-one bank scenarios compare current controls, valid replay payload and
  private progress against the balanced parent, and check the new output equals
  the existing sticky register. These are simulation checks, not formal proof.
- Both actual generated FFT campaigns match 64,512 numerical words and retain
  4,178 service clocks (23.874 us at 175 MHz; budget 5,215 clocks).
- All 43 inherited fault/reset/delay cases plus 11 new boundaries pass. New
  cases cover first/middle/last capture, seal, replay, product publication,
  output publication, forward/inverse completion and both pending reset paths.
  Each recovers 512 correct fresh reads and one real release after reset.
- The actual observer checks 88,545 healthy cycles and 602,846 auxiliary cycles.
  Auxiliary stimulus exercises 38 new bank-fault edges, two same-edge private
  completions and 11 delayed guard observations. Current publication remains
  fenced, registered status prevents reuse, and global fault meets its bound.

The initial component run failed elaboration in 21 cases because its wildcard
port connection lacked a `private_fault` wire. Only the testbench connection
was corrected. Both the failed run and the 46-pass rerun are retained; actual
simulation and synthesized source inventories did not change.

## Routed result: reject timing promotion

The unchanged Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe
routes all 8,663 nets without routing errors, but setup timing regresses:

| Metric | Balanced parent | Private status |
|---|---:|---:|
| WNS / TNS (ns) | -1.420 / -420.378 | -1.608 / -640.951 |
| Failing setup endpoints | 939 / 14,505 | 1,344 / 14,519 |
| LUT / FF | 2,805 / 5,912 | 2,767 / 5,916 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Hold +0.053 ns and pulse +1.830 ns have no failures. Combinational/latch-loop
counts are zero. There are still 114 unqualified inputs, 124 unqualified outputs,
nine CDC-3 observations and 208 CDC-15 warnings; no CDC-10. The scalar global
fault register remains the direct synchronizer source. CDC replicas include
the reset release source and output descriptor bit 3. These are observations,
not full-board CDC or I/O qualification.

The worst 175 MHz path is `epoch_barrier/fast_release_reg_replica/C` to
`product_identity_stage/output_identity_good_reg/D`: 7.088 ns data delay,
12 logic levels (six CARRY4), 69.454% routing. It traverses current stage fault,
first-word metadata-load selection, the wide reference mux and identity equality.
The next path is input-guard fault to product-stage occupancy (-1.355 ns).
Fewer LUTs did not deliver better timing. This candidate is retained as a
functionally tested experiment, not a replacement for the better timing parent.

Next isolate the product identity reference-selection cone. Compare incoming
metadata against both held and retiring-first-word references in parallel, then
select a one-bit certificate. First establish exact four-state equivalence,
including X/Z selector/metadata, first-word same-edge refill, final hold,
fault/reset and no publication leakage. Repeat actual arithmetic/boundary tests
and routing before judging improvement. Do not blindly remove metadata checks,
relax clocks or weaken current publication fences. Local reset/fault fanout and
held-metadata CDC qualification remain separate outstanding work.

Routed DCP: `3ff64b28ed9298c55c7752add0c784f95178b8dd1cd2e53ebc2e46e051206f7d`.
Synthesis took 101.604 s; routing took 57.732 s. These are experiment runtimes,
not deployment estimates.

## Reproduction and pins

Branch: `codex/starlink-rx-only-do-not-merge-forward-private-status`.
Prepared source inventories:

- Main: `8470f72fc4ac863b35ce398bf55d559d88394bb7a2934a3527eb30678d5cb2cd`.
- Auxiliary: `5d9309f68caf4793e7dc23f86f600de78b36936d414ff8e5b6df5484cfd497f5`.
- Synthesized DCP: `7574f92fbd404a6ea76c7c1ed4a9417fc49ecac9a29a2109d52b394e4337f5a3`.

`tools/forward_private_status_experiment.py` prepares, runs and audits actual
main/auxiliary simulations and synthesis. `tools/route_forward_private_status.py`
requires matching runtime sources, fresh numerical and boundary witnesses and
the pinned synthesis DCP before routing. `tools/audit_staged_fft_route.py`
cross-checks checkpoint identity, routing and timing reports. The recording
helper retains failed component evidence as well as passing verification.

No radios, PPU or main branches were modified. Primary HDL stays pinned to
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Deployment still requires full receiver
timing/CDC/reset qualification, actual 60 MS/s calibration, continuous RX and
IIO/Ethernet verification, then pinned reversible PPU deployment to `.18` before
Ethernet-only `.17`. `.14`, `.20` and `.21` remain excluded.
