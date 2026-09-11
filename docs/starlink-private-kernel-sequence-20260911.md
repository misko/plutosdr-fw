# Private kernel sequence — DO NOT MERGE

Built on private-final-capture FW `565dd5c45` / HDL `e200100db`. Those sources
passed actual FFT and 417 tests, with WNS -2.005 ns / TNS -634.847 ns / 856
failing setup endpoints. The older private-descriptor-only reference remains
available at -1.969 ns / -813.676 ns / 914. Neither is deployment-qualified.
New branch: `codex/starlink-rx-only-do-not-merge-private-kernel-sequence`.

## Implementation contract

The default-off PRIVATE_SEQUENCE_ADVANCE option updates the kernel's hidden
bin index, expected next-block start and have-previous flag on a caller-owned
private offer with actual input capacity. A nine-bit increment wraps at 511;
the last private offer updates next start by 447 and marks previous-block state.
The existing public checker uses pre-edge state, unchanged input_valid, and
unchanged per-bin, TLAST, exponent, block identity and next-block stride checks.
Only original successful public acceptance can assert output-valid or completion.

The result guard supplies a structural private offer from its held checked
forward word. Final offers still wait for original final qualification, including
status, exponent, counts and final fence. Public retirement is unchanged. The
top applies actual product-bank capacity and registered fault quarantine to
both paths. Any private/public divergence must remain quarantined until common
reset; a private advance is not permission to publish or start a new job.

This extends the earlier isolated ordinal idea to the adjacent 64-bit next-block
state and composes it with private final-data capture. The prior ordinal-only
route was worse, so no physical improvement is assumed from functional proof.
Default-mode behavior and the original public output/control interfaces remain.

## Executed verification

Eight local tests pass in 0.61 s. The comparison compiles the pinned original
ROM and three candidate modes, checks public controls and valid/stalled data
cycle-wise, and retains 4096 healthy lookups, four malformed cases and flush
recovery. Additional cases check wrong next-block stride after a complete block,
an unpublished first offer, and an unpublished final offer after 511 public bins.
The final private offer advances all hidden sequence state but neither public
acceptance nor completion, and all sequence state clears on flush. The local
harness withholds future offers to model caller quarantine; actual FFT tests
below verify the caller itself. Seven unsafe variants are rejected: no advance,
ignored capacity, private publication, missing flush, missing next-start capture,
missing previous flag and wrong stride. No test deadline was relaxed.

Source/lint preflight passes two tests. Actual generated FFT passes in 118.22 s;
synthesis passes in 98.33 s. Before/after source hashes match. All 64,512 records
match the pinned reference; the numerical CSV is byte-identical. Service remains
3659/3659/4927/11727/3659/3659 clocks, with the deliberate reader-stall context
excluded from the unchanged 5215-cycle service bound.

All earlier reset/fault/admission/completion/replay/writer/descriptor/final-capture
tests pass. A per-cycle monitor verifies all private sequence advance/hold state,
requires a private offer for every public acceptance, and checks healthy public/
private handshakes are identical. Healthy counts: 9216 advances, 98,246 holds,
18 final next-block updates. Six actual cases cover mid-word vendor fault,
product framing fault, duplicate status, delayed legal final status, 16-clock
held-final capacity stall, and a vendor fault precisely on a qualified final.
Fault cases show private state advancement without public acceptance/completion,
then 100 clocks with no further input, job, publication, read or release. Legal
late/stalled finals each yield 512 correct reads and one real release. Total
campaign receipts including aborted jobs: 106 admissions, 77 completions.

## Route and regression: lower aggregate deficit, still FAIL

435 combined tests pass in 55.58 s (417 inherited, eight sequence tests and ten
new evidence-parser controls). Missing final-fault cases, invalid coverage,
duplicate/missing receipts, publication leakage and unchecked next-block state
are rejected. Actual FFT, synthesis, route and all test runs pass on first use.
Routing completes in 55.82 s; independent source/checkpoint/report audit passes.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private descriptor capture | -1.969 ns | -813.676 ns | 914 |
| Plus private final-data capture | -2.005 ns | -634.847 ns | 856 |
| Plus private kernel sequence | -2.047 ns | -550.201 ns | 825 |

TNS improves by 84.646 ns versus the parent (about 13%), and 31 fewer endpoints
fail, but worst slack regresses 0.042 ns. Retain all references; this is a mixed
result, not timing closure or a deployment promotion. 825/13800 endpoints fail.
Hold +0.058 ns and pulse +1.830 ns pass, with 8363 nets routed and zero errors.
Resources: 2770 LUT / 5668 FF / 21 DSP / 15 RAMB18, zero RAMB36. Diagnostic
100/175 MHz clocks are unchanged. Five critical CDC findings, 208 warnings,
and 114/124 unqualified board I/O remain. No timing waiver was introduced.

The worst path is now publication phase -> output-bank metadata mux/comparison
-> guard/shared current-fault aggregation -> registered descriptor certification.
It has eleven logic levels, 7.706 ns data delay, including 5.886 ns routing.
Reducing private enables has lowered the aggregate deficit without breaking
this cross-module current-fault feedback dependency.

## Next gate

Review descriptor certification and registered quarantine as a complete
admission boundary. `descriptor_certified` currently captures
`preparation_valid && !any_fast_fault`, even though the next admission also
requires current validation and registered quarantine gating. A private descriptor
snapshot may be separable from public authorization, but that needs an exact
cycle proof: a fault on snapshot or consumption must prevent every job/config
start, cancel stale receipts, and require a fresh epoch. Preserve immediate
publication vetoes and detailed fault capture. Do not simply delay the global
fault line or waive it. Retest actual FFT/fault/reset/expiry before routing.

## Identity and remaining scope

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-sequence-{prepared,actual,synth,route}-v1` and
`staged-sequence-{unit,preflight,regression}-v1` with XML receipts.
Prepared inventory: `abdac9894243bc6d7c3c573095fa332068a14e641f044205e40925abeb432606`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Original ROM: `0b4ee87d93d61c6fa12ee9992aa517a3a8be568835075531d9af4453f4ec80e5`.
Synthesis DCP: `bb99304bab866708ee00e50369f7778eac121cfae9a74fb947d3f9b8e456181a`.
Routed DCP: `4c58e354dbe421a671f9f1a292d6e6a685ae89be50230a3a86d2b83a2e3cca94`.

This is an isolated FFT/buffer test, not continuous 60 MS/s reception or physical
signoff. Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection
remain required. Full receiver route/CDC/reset/board constraints, sustained
capture, actual RX calibration at 60 MS/s and Ethernet/IIO verification remain
before `.18` reversible canary and `.17` PPU Ethernet-only deployment with pinned
rollback. Final verification remains a 300-second scan with 120 ms valid dwells
and blind host GLRT comparison. No radio, PPU, main or production HDL changed.
