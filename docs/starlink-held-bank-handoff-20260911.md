# Whole held bank handoff — isolated subsystem, DO NOT MERGE

Parent FW `e25e9c5bf` / HDL `b41d5115b` is the rejected metadata-only candidate:
-2.203 ns WNS / -672.268 ns TNS / 796 failing endpoints. Compare also against
guard facts (-1.340 / -463.636 / 821) and private certification
(-1.452 / -451.168 / 704). None has timing closure or deployment qualification.

## Implementation and frozen gates

For registered scheduling only, use the inverse guard's held data, position,
last and metadata during private writing and replay. Combine its private-valid
with replay-valid using OR. Completion retires the inverse guard on the edge
that makes publication ownership nonempty. During that ownership, the guard
must be inactive with private-valid zero and its final payload held. Replay-valid
must be zero when the publication adapter is empty. These are required temporal
invariants, not assumptions that a wiring truth table alone proves.

Structural reasoning to check against the live witness: top-level completion
acceptance includes `guard_commit_out[1] && output_bank_ready &&
output_complete_ready`, which implies the guard's own final handshake through
`inverse_guard_ready`. That edge clears its active state and moves the adapter
out of EMPTY. Guard payload capture requires active and no sticky fault; raw
events after retirement cannot overwrite it. Descriptor ownership blocks a new
inverse allocation until actual release. Replay-valid requires nonempty REPLAY
phase. Thus a healthy accepted replay should see the same final word captured
by the original adapter; current fault gates still decide whether it publishes.
This is code-based reasoning, not a standalone formal proof.

Leave the original selections for nonregistered callers. Do not change current
fault diagnostics, same-edge public commit vetoes, descriptor validation,
allocation, publication or real reader ACK. The metadata-only parent source
inverse is retained on its pinned snapshot; the new whole-top inverse checks
the handoff-only delta. Current metadata wiring checks remain live.

The actual-XFFT bench's second real bank now uses ALL original inputs (valid,
data, position, last, metadata), not the candidate-selected inputs. Its outputs
authorize nothing. Compare writer state/faults/ownership and reader output as
before; on rising edges compare input validity case-exactly, assert mutually
exclusive ownership, and compare every offered valid/ready payload. Maintain
the existing numerical, fault, reset, final/status stall and reader-ACK tests.

Six added integrated cases: orphan raw output immediately after retirement;
orphan raw output at replay; orphan status at replay; 16-clock replay pause and
resume; fast reset during that pause; slow reset during that pause. A pause
holds private-ready and actual commit wires low together, not descriptor
registers. Late-event cases test the unforced immediate publication veto and
unchanged retired payload. Reset cases test cancellation while paused. Each
case must finish with 512 correct fresh reads and one actual release; cancelled
cases also require 100 clocks without stale output/reuse. These injected stalls
are a verification mechanism, not new production flow control.

Require all 64,512 numerical records and six service intervals unchanged,
complete regression pass, source-matched synthesis and route at the unchanged
100/175 MHz diagnostic clocks. Compare WNS/TNS/failure counts against all three
references. No new receiver features or clock relaxation to pass this gate.

## Initial verification

23 unit/preflight tests pass in 10.60 seconds. New tests include a complete
runtime inverse, 23,552 four-state wiring/fallback cases and five rejected
mutations (AND of offers, wrong data/position/last, removed fallback). This is
wiring evidence; actual simulation must separately establish ownership safety.

Prepared inventory: `d84b6a46c5b376a17523e7cc8287aa075af71ac17fc0630205a77d65eb088e78`.
Actual FFT passes in 176.38 seconds; source-matched synthesis passes in 97.45
seconds, both first attempts. All 64,512 records match with byte-identical CSV
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service remains 3659/3659/4927/11727/3659/3659 clocks; the 11727-clock context
deliberately pauses its reader for 9000 clocks and is excluded from the
5215-clock diagnostic service bound. This does not measure continuous RX.

All six new cases pass with fresh 512-word/one-release recovery. The rising-edge
handoff monitor checks ownership/validity for 441,088 cycles and compares 100
accepted replay offers, including deliberately repeated private final rewrites
while commit is paused. These are not 100 published frames. The original-input
real-bank witness additionally passes 441,206 falling-edge writer-state checks,
64 first-word, 168 final-word, 104 replay, 19,446 valid/ready reader and 21,928
stalled-reader observations. Falling-edge counters are observations, not unique
transfers. Existing fault/recovery tests also pass; 159 admission and 109
completion receipts include aborted work. No board or deployment claim.

Synthesis DCP: `90b55ce275f6811ad6d39adf02758b5eaec26bd823ecd26ed436d6c828cd3ae6`.
## Completed route and regression: not timing-closed

496 combined regression tests pass in 71.28 seconds, including ten new audit
controls rejecting missing/duplicated cases, insufficient coverage, disabled
offer/veto checks and incomplete fresh recovery. Route completes in 51.06
seconds; independent source/checkpoint/report audit passes. Actual FFT,
synthesis, route and unit/regression runs all pass on first invocation.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification reference | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |
| Metadata-only parent | -2.203 ns | -672.268 ns | 796 |
| Whole held handoff | -1.868 ns | -565.807 ns | 720 |

The whole handoff improves all three metrics versus its metadata-only parent
(WNS +0.335 ns, TNS +106.461 ns, 76 fewer failures), but remains worse than the
private-certification reference on all three metrics. **Do not promote as the
timing reference or deploy.** Retain the independently tested ownership
simplification for a source-matched future composition, not an assumed benefit.

720/13756 setup endpoints fail. Hold +0.058 ns and pulse +1.830 ns pass. All
8272 nets route with zero errors. Resources: 2699 LUT / 5650 FF / 21 DSP /
15 RAMB18, zero RAMB36. Compared with metadata-only: +30 LUT and -36 FF.
Diagnostic clocks stay 100/175 MHz; no new waivers. Five critical CDC findings,
208 CDC warnings and 114/124 unconstrained board I/O remain.

Worst path: registered scheduler held phase -> input metadata identity/checker
fault logic -> inverse guard awaiting-ACK D. Nine levels, 7.575 ns data delay,
6.003 ns routing (79%). Next (-1.832 ns) reaches output descriptor pending from
inverse sticky fault through completion qualification. The old publication
payload-mux path is no longer the worst reported path; this does not prove all
paths involving publication are closed.

Next inspect the inverse ACK/reuse boundary and why current input-identity
validation reaches it after inverse input retirement. Establish its exact
phase/ownership contract before any simplification; retain orphan/raw-event
detection, sticky diagnostics, current public vetoes and real reader release.
Compare any change against the retained private-certification reference as
well as this handoff candidate, with actual FFT and unchanged route constraints.

Routed DCP: `de1227a92ad555224164cda294cd111a8138ca57603a6449520acc976de76c76`.
Evidence folders: `staged-heldhandoff-{prepared,actual,synth,route}-v1` and
`staged-heldhandoff-{unit,regression}-v1`, with XML receipts, under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

## Required deployment end state

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s calibration and Ethernet/IIO qualification precede
`.18` reversible canary, then `.17` PPU Ethernet-only deployment with rollback.
Final test remains a 300-second scan with 120 ms valid dwells and blind host
GLRT comparison. No radio, PPU, main or primary production HDL changes here.
