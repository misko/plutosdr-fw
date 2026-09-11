# Completion mailbox stage with actual FFT — DO NOT MERGE

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-completion-mailbox-stage`.
Parent FW `a2313deebda25a90d9d70658d3ee98f3e4581b91`, HDL
`d999ec011fe9c8e116d453878474a3099c406cec`.

## Result and scope

Integrated and tested a one-entry completion receipt with the actual 512-point
FFT, descriptor ledger and payload buffers, then routed that subsystem before
adding features. Functional verification passes. **Setup timing still fails**;
this is an experimental candidate, not a deployable receiver or a production
promotion. Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection
remain requirements; neither path was removed to obtain this result. No further
TX removal, radio access, PPU/main change or primary production HDL change.

## Small runtime change

The new `starlink_pss_completion_mailbox_stage` copies the original adapter and
adds one `complete_pending` register. Completion acceptance immediately reserves
the payload bank, captures its tag/final word/request identity and prevents
further completion or allocation while the receipt is pending. On the following
healthy edge the sequencer consumes the receipt and enters COMMIT. Payloads stay
frozen throughout pending ownership and the original COMMIT, replay, actual
publication, reader ACK and RELEASE sequence. Current fault vetoes still apply;
fault holds pending ownership until coordinated reset purges the epoch.

The private receipt is not publication evidence. Only the actual bank request
transition proves publication. No clock, arithmetic, buffer size or timing
exception changed. The top changes only the adapter instance's module type.
Exact inverse tests preserve the parent top and all other runtime modules.

## Verification and diagnostics

- 720 regression tests pass in 86.37 s. New component tests include 24 real-bank
  combinations of cancellation boundaries, reader stalls and both private-final
  capture modes; four unsafe variants are rejected.
- The first actual main/auxiliary tests exposed an outdated assertion: it used
  nonempty sequencer phase as the ownership indicator. Ownership now starts one
  edge earlier, with the pending receipt. Three monitor predicates were changed
  to the actual `publication_busy` signal; accepted-payload equality checks and
  all inherited cases remain. All 22 runtime modules are byte-identical between
  prepared V1 and V2. Rejected V1 logs are retained and V1 was not routed.
- 40 focused tests pass after that monitor correction. This is not a second
  run of the complete 720-test suite.
- Main V2's simulator and Tcl reported success, but its launcher exited 143
  without saving `outcome.json`. The launcher was verified absent before a
  fresh run. Its cause of termination is unknown; the missing record is not
  substituted with an inferred successful outcome. The first audit attempt
  failed on that missing record (17 pass, one fail), and route did not start.
- Fresh main V3, using the same prepared V2 sources, completes with a successful
  source-bound outcome in 207.77 s. All **64512 indexed numerical comparisons**
  pass. CSV bytes differ from the parent because scheduling changes; numerical
  equality is established by the indexed comparison, not a byte-identity claim.
- Service clocks are **3663/3663/4929/11729/3663/3663**: one extra clock in normal
  contexts, unchanged intentional stall contexts. Normal service remains below
  the existing 5215-clock coarse bound; this is not continuous-RX throughput
  or 750 measurements/s proof.
- Main receipt witness: 70 accepts, 67 healthy consumes, 86469 held-payload
  checks. Auxiliary V2 passes in 145.38 s with 51 accepts, 48 consumes and 40730
  holds. Three new pending-boundary cases inject vendor fault, raw reset and FFT
  reset; each verifies cancellation and fresh 512-word/one-release recovery.
  Inherited output, ACK, forward and product boundary cases still pass.
- Synthesis V2 passes in 98.84 s. Eleven new actual-evidence tests and seven
  overlapping archive tests pass (18 total in 1.43 s). Missing, duplicate,
  incomplete and incorrect receipt evidence is rejected before route. Distinct
  regression/new-evidence total is **731**; repeated subsets are not added again.

## Unchanged-constraint physical result

Vivado 2022.2, xc7z010clg400-1, original 100/175 MHz OOC recipe, two threads.
Route completes in 49.63 s. A read-only query checks the exact old metadata
source, `output_descriptor_payload_reg[4]/C`, and these actual endpoints:

| Endpoint | Measured result |
|---|---:|
| `output_control/phase_reg[0]/D` | No combinational timing path (parent −1.736 ns) |
| `output_control/complete_pending_reg/D` | +0.096 ns |
| `output_control/publication_seen_reg/D` | −0.008 ns |

The direct phase feedback is cut, but adjacent completion/publication logic
still has a small violation. This does not mean all paths to phase pass.

| Whole subsystem | Balanced parent | Completion receipt |
|---|---:|---:|
| Worst setup slack | −1.736 ns | −1.560 ns |
| Total negative slack | −430.075 ns | −479.076 ns |
| Failing setup endpoints | 715 | 837 |
| LUTs / registers | 2727 / 5789 | 2760 / 5790 |

All 8405 nets route without errors. Hold +0.071 ns and pulse +1.830 ns pass;
21 DSPs and 15 RAMB18s are unchanged. 114 inputs and 124 outputs remain
unconstrained in OOC. The worst same-domain path is now
`slow_reset_fast_reg[1]/C` to `admission_gate/snapshot_good_reg[0]/R`:
nine logic levels, 6.666 ns data delay, including 5.094 ns routing (76.4%). It
crosses epoch/reset qualification, product readiness, completion and admission
logic. This is a synchronous control path, not grounds for a broad false path.

Read-only reset inspection preserves exclusive first-to-second synchronizer
fanout and registered purge signaling. CDC inventory remains nine CDC-3
informational paths and 208 CDC-15 bundled-data warnings, with no CDC-1/CDC-10
critical findings. Bundled-data physical qualification is still outstanding.

## Next gate, before more features

Retain this measured candidate and the parent; do not promote based only on
better worst slack. The next bounded experiment should separate private
admission snapshot housekeeping from the long epoch/readiness/current-fault
network, with explicit local ownership. Any deferred private clear must leave
current public cancellation and reset behavior intact. First prove equivalence
at reset, fault, stall and ownership boundaries, then run the same actual FFT
and unchanged-constraint route. Also retain the −0.008 ns publication-seen path
as an explicit endpoint, rather than assuming it disappeared with phase.

Only after subsystem closure: full receiver integration, board clocks, full
timing/CDC/reset, actual native 60 MS/s RX calibration, sustained 2.5 MS/s IIO
and Ethernet, then reversible `.18` canary and `.17` PPU Ethernet-only deployment
with pinned rollback. The 120 ms valid dwell / 300 s scanner and blind host GLRT
comparison remain required. None of those deployment gates is established by
this OOC experiment. No radio was flashed or touched.

## Reproducible pins

Evidence root: `/dev/shm/starlink-completion-stage.rTnPYQ8U`.
Prepared V1: `ae1a66db7b8c98f7832ebdc64b32ee247e9db4ef3faf27ac6577ce6d48a4e4eb`.
Prepared V2: `579b4b69fee7eb67a20befbb901d53b0ff033dd7305603e57b532d950d47114c`.
Successful main: `sim-v3`; auxiliary: `ack-v2`; synthesis: `synth-v2`.
CSV: `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.
Synth DCP: `2e7fafe7f1c7bf60ffbc7e69a9949a5aebf61d60c375f04352725f5c5cc2694a`.
Routed DCP: `0a25faf068b197ffa2daa6d24f548a4bf446e32b38642c36ce71bda9deed35b5`.

`tools/record_completion_stage_evidence.py` rechecks outcomes, source pins,
numerical comparisons, test counts, route metrics and read-only inspections.
The verified archive retains rejected/incomplete diagnostics and the complete
successful evidence. Duplicate vendor VHDL is kept once after byte-equality
checks; regression-only duplicate CSV/DCP files are omitted from the package.
No raw evidence is deleted. Firmware remains DO NOT MERGE; goal remains active.
