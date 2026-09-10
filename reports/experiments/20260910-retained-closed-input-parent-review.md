# Combined retained-output control candidate: offline PASS

The default-off private-descriptor offer and closed-input cutover view are now
implemented as isolated candidate RTL. Root independently passed the 39-test
closed/combined gate in 5.90 seconds (original process 3251, terminal exit 0).
All 49 source pins remained unchanged, including all 40 from the previously
passing private-only gate. No vendor FFT, synthesis, route or radio was run
for this gate. The latest physical result remains **WNS -4.068 ns, FAIL**.

## What changed and what did not

The private offer separates inactive descriptor capture from qualified job
admission. The closed-input view duplicates the original cutover predicate
with only its two certified input strobes set to zero. It is consumed only by
the completed-input public-return paths. Full current diagnostics, sticky
reasons, admission/configuration and all ACK/reader-release paths are retained.

Enabled return visibility requires a known-one completion certificate. This is
an explicit fail-closed tightening for X/Z, not four-state equivalence. It
preserves known 0/1 behavior and gates mailbox input-valid, mailbox commit-valid
and forward retirement. Private payload storage is not publication authority.
ACK must not depend on the shared core's completion bit: an old retained inverse
can be acknowledged while the next forward input is still incomplete.

Both flags default off. Seventeen closed-input edits and eleven preceding
private-offer edits invert to the four original files. This establishes the
source-bound named-port default, not blanket positional port/parameter ABI
compatibility. Original qualified runtime files and the passing v5 actual
package remain untouched.

## Independent evidence

- All four flag combinations crossed with three reader-stall profiles: twelve
  complete scripted compositions. Root checked each log for the two accepted
  descriptor/real-ACK witnesses and the closed-input witness, without fatal
  output. Original two-guard and arithmetic shadows remain in these benches.
- Real unchanged input guard: 512 admitted input beats, final input observed
  before and after its registered completion update, then 255 closed-state
  perturbation checks. Duplicate-start detection and reset purge remain live.
- Real held-return states: eight known-certificate comparisons, four original
  X-to-zero visibility cases, four naive zero-to-X counterexamples and twelve
  raw-fault checks; actual ACK at completion=0, sticky diagnostics and reset.
- Executed defects are rejected: missing known-one visibility gate, incorrectly
  tying ACK to completion, and reopening the completed input slot. Strict
  inverse and invalid-parameter rejection checks also pass.
- All twelve compiled compositions retain 2480 declared state bits and three
  payload arrays. This is not a mapped utilization or timing claim.

Root also executed a separate old-module-versus-new-module predicate test, with
the two certified strobes tied to zero. It passed 8192 Boolean valuations of
13 predicate controls/state bits and 212992 single-X/Z perturbation executions
(including repeated valuations), 221184 comparisons total. The original full
predicate, candidate full predicate and candidate reduced predicate agreed.
Three separately compiled dropped-term defects (vendor-fault, early-result and
known-control checks) each failed the exact mismatch detector.

That algebra test deliberately forces internal predicate state. It is not a
reachable-protocol proof or exhaustive multi-X/Z test. The real input-guard
and composition witnesses supply the separate phase premise: once registered
completion is known one, both certified strobes are zero, even with unknown
unrelated input fields. The final input's pre-update edge still uses the full
current diagnostics.

An independent source reviewer found no remaining handwritten-RTL combinational
product-read-metadata path into the reduced completed-return cone. Full metadata
checks intentionally remain on diagnostics, admission and ACK. This excludes
vendor-core internals and is not a measured synthesized-cone or routing result.

## Preserved first failure

The first closed-input test attempt (`retained-closed-input-tests-v1.Qiqlxp0W`)
had 20 passing tests and 16 compilation failures. An added composition witness
used macro `D` after the original bench had undefined it. Only the new witness
references were changed to literal hierarchy; the four runtime files were not
changed. Original failure logs, source-before hashes and XML remain preserved.
The subsequent developer gate passed 39 tests in 5.89 seconds, before root's
independent repeat.

## Next gate, not deployment

Actual-FFT **preparation** is authorized for the combined candidate. Reuse the
passing v5 seven contexts, numerical vectors/arithmetic, frame and full CSV
checks, service limits and exact FFT factory. The original full completed-input
fault expression must remain independently checked; feeding only the candidate's
reduced signal into both sides is not sufficient reference evidence. Keep the
existing full public-output shadow first; any actual invalid-private-metadata
difference requires a preserved counterexample and a narrowly reviewed witness.

The launch needs explicit two-flag selection/readback and frozen source/profile
inverses. Root owns any actual vendor execution. Fresh physical closure,
175 MHz board-clock integration, CDC/reset/I/O qualification, continuous
15/30/60 MS/s acquisition/native fine, independent 2.5 MS/s IIO comparison and
the eight-target 120 ms-valid-dwell/300 s scanner remain required before a
reversible `.18` canary and `.17` PPU Ethernet deployment. No radio was changed.

## Exact sources and recovery

Recovery root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`.

- `retained-closed-parent.X69SNqBk`: independent 39-test gate, 49 source pins,
  source snapshot, generated benches, logs, XML and twelve-composition audit.
- `closed-algebra-parent.ycBAqmQD`: independent real-module algebra bench,
  source pins, four compilation/execution records and mismatch controls.
- `retained-closed-input-tests-v2.gu0WbmpG`: developer 39-test gate.

Runtime SHA256 (in `retained_output_closed_candidate`):

| File | SHA256 |
|---|---|
| `starlink_pss_core_job_cutover.v` | `6f3a42178b824c28f0f6bfe3c4aeb56a2c23b84fc9aa38ab3be0d5609c4cba19` |
| `starlink_pss_fft_bank_owned_retained_output_probe.v` | `62f7941bc76ac320bfdee235aeae9a5f3c3bd86e251e92f571162f8183a0abec` |
| `starlink_pss_fft_retained_output_impl.v` | `1d01972d11486772b627a3afdd594f06e41c0f98b830288e93b371af0506ef1e` |
| `starlink_pss_result_guard_owner_view.v` | `53c336df4dd378a27b12f7c4d382d25290c81c0881b8e6c4f914faa67482d320` |

Closed inverse SHA256:
`df227b48473b22e6bb02db54400d214c6e159a1daba241a4bd06f9fc17cff2e6`.
Helper SHA256:
`98169f56d5e842ed623e74c5c96944e8b24a009fb1740ba648672b8615f7107e`.
Test SHA256:
`d27fdb6f727e0d431034a103d488b7b26bb539ca9a8d80a7eb90ff7d0bc41673`.
