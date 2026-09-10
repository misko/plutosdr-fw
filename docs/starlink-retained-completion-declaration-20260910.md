# Retained-output startup declaration repair: offline preparation

This is the parent-authorized two-edit declaration repair, not an actual FFT
success. No vendor run or push was performed in this lane. All preceding
failures and immutable bundles remain intact.

## Observed failure and diagnostic scope

Parent actual 74560 reached simulation and failed at fast cycle 31,
174285723 fs, before any FFT admission. Parent copied-snapshot diagnostic
42893 reproduced the same assertion without changing runtime, stimulus or
checks. Its returned simulator exit zero is not a numerical PASS. Recorded
completion_accept, completion_receipt and cutover.producer_closed were `Z`;
cutover.known was 1, raw controls were zero, and job/config accepts were zero.
The cutover latched reason bit 0 and correctly propagated failure to both
guard owner views. The shadow counters were known (payload_checks=2,
forward_checks=61); the compiler initializer warning is not an established
problem and no counter initializer was changed.

Parent read-only first-fault history found completion_accept and producer_closed
`Z` at all 95 sampled times, fast_running rising at 162857151 fs, and reason
bit 0 latching at 168571437 fs, the first enabled sample. The observed
completion_receipt value is consistent with its unchanged registered assignment
sampling that `Z`; its declaration already precedes use and its reset remains
zero. Do not infer a vendor reset-flush latency failure from this evidence.

The actual compiler had warned that completion_accept was implicitly declared
at its earlier module-port use, then declared with an assignment later. The
repair makes this net declaration explicit before either use and expresses the
same later driver as a separate continuous assignment. Actual confirmation of
the repaired elaboration and startup behavior remains a separate gate.

## Exact source scope

Tested FW `946ea9fa747097a5a2730acca93ae39b656cf232`, HDL
`c02fb48b72c4abcb43bc2aab4f7b0d0511ef1b52`.

Only runtime file changed:
`hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_fft_retained_output_impl.v`.

1. Add `wire completion_accept;` before its first module-port use.
2. Replace later `wire completion_accept =` with `assign completion_accept =`.

The full RHS, all registers/resets, state transitions, guards, timing and
arithmetic remain byte-identical. Runtime SHA256 is
`2f11bc7e08e907209336775877155839becf45f8015126bd99769c2dccc550d4`.
The strict two-edit inverse recovers entire original-source SHA256
`3d494d7ce8a6cc8f863b4d1ec0b465c084082d3eb64956c581488245042d6da5`.
It rejects absent/duplicate/late declaration, absent assignment, changed RHS,
changed reset, changed guard binding and any unrelated body edit.

`retained_output_actual.verify_originals` applies this inverse only to that
exact original-46 path and requires the exact historical expected SHA. The
other 45 historical files retain direct byte-hash checks. The original 46-file
manifest is not rewritten. The new inverse helper and test are explicitly
added to the bundle closure; there is no generic source-hash exception.

## Executed offline gate and fresh bundle

Original handle 48998 terminal 0: **155 passed in 13.36 s**. Evidence root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-declaration-final.b0EnWxEX`.
Exact pytest scope:

```text
tests/test_starlink_retained_output_actual.py
tests/test_starlink_retained_output_actual_bundle.py
tests/test_starlink_retained_completion_declaration.py
```

Python `-B`, cache disabled, sanitized Python/loader environment, unique
recovery TMPDIR/basetemp, full pytest.log/results.xml preserved. This is
113 unchanged actual-harness/script/parser tests, 31 bundle/runner tests with
updated closure counts, and 11 declaration tests. Ruff F/E9 passed.

The exact old/new completion expressions compare over all 32,768 known-state
combinations plus 352 targeted X/Z controls (33,120 total). A separate read-only
witness on the unchanged seven-context scripted stimulus checks top/port
identity, known-zero completion in RESET0/RESET1/WAIT_BANK, and receipt equal to
the previous sampled completion: 89,474 enabled checks, 20,188 idle checks.
All seven contexts, 19 complete pairs, two aborted F prefixes and exact original
numerical inventories still pass. This is explicitly **not XSim reproduction**.

New prepared bundle:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-output-actual-prelaunch-declaration-v3`.
External manifest SHA256:
`cb3bfc9af54809f67c95e20fd642019c1b953f3a51f40bf3a75e3a502eabd583`.
Source signature:
`de2dfda5aa7c77d890c7f06ffb3b3e3e065bc83f0c76556a55cee206ba9dc75a`.
It contains 73 sources, 76 file receipts and manifest (77 regular files).
Manifest bytes exactly match the test-generated bundle. Frozen resolved-base
Python CLI from `/` with `--live` passes.

Relative to language-v2, exactly four common sources change: the runtime,
actual helper, bundle helper and bundle test; two sources are added: inverse
helper/test. All other 67 common sources, expanded bench, profile, environment,
eight goldens, ABI, recipe, parser, runner and clock/stimulus sources are
unchanged. Both older bundles remain independently receipt-verifiable; their
historical live checks must not be called unchanged after this approved delta.

No actual run, default promotion, clock change, new payload bank/DSP, lower-rate
qualification, continuous native/canonical-source claim or RF claim follows
from these offline results. Parent review of the fresh source-specific bundle
precedes any actual recompile/invocation.
