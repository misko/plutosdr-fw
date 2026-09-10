# Parent review: data-only timing cut and concurrent native test

Review date: 2026-09-10 UTC. This is source-specific functional evidence and
authorization for one diagnostic physical measurement, not a release gate pass.
No receiver, radio, PPU, main branch, or existing deployment was changed.

## Reviewed timing candidate

Alternative FW `c62118a9a8fd5056f3376a526c36157e004842ae`, HDL
`97adf891ee4cece8634c0bf9bc6694a1df58b9aa`; tested design RTL remains
`b7dac8024d5870c9b2909188dfa0a7766c3f7a39`.
Worktree: `/tmp/starlink-coarse-alternatives.Y3JzOI/completed-input-fence`.

The parent inspected the four-module delta against `7ee87258`, the literal
inverse tests, immutable reference chain, occupied-stage and invalid-payload
rules, both actual-core terminal logs, and the study report. All416 entries in
`hdl/library/starlink_pss_acquisition/evidence/payload-bubbles-v1/SHA256SUMS`
independently verify. Parent reran
`python -m pytest -q tests/starlink_oracle/test_payload_bubbles.py` with the PPU
venv interpreter: **19 passed in1.80s**, including all eight option combinations
and deliberately broken comparison/overwrite/invalid-token variants.

Both original actual175 runs pass: default324,592 independent chain checks,
registered586,260. Both complete control CSV hashes match the prior held-
preflight run. All prior numerical, guard, fault, retirement and boundary checks
remain in the unchanged stimulus. The additional invalid-cycle arithmetic
switching cost is unmeasured; no mapped-path improvement is inferred from RTL.

The alternative's broad result remains752passed/10physical-skips/7failures.
Its seven failures open missing files in an uninitialized Linux submodule.
Parent verified the four affected test files are identical to primary
`fa9120035907663f08d3af7a3f384bcd07b36d39`, whose initialized Linux is exactly
`4357f41a721df9d89a66be7a2a3f921a71d46bad`, then reran the exact seven tests
there: **7 passed in0.92s**. This confirms the reported dependency distinction;
it does not replace the failed alternative run with a wholly-green result.

## Authorized physical experiment

One synthesis from the passing `payload-actual-v1` frozen source, then one
diagnostic route of its successful hash-pinned checkpoint. Keep existing
100/175MHz constraints, strategy, scripts, two-thread limit and zero-blackbox
gate. Verify all seven source files before and after. Add a separate read-only
final DSP AREG/BREG/MREG and enable-driver inventory; do not alter implementation
to obtain the inventory. No retries, timing exceptions or receiver promotion.

Original synthesis handle70333 targets
`/tmp/starlink-completed-input.5EaJuD/payload-bubbles-synth-v1`.
It completed exit0 at04:32:40 UTC:1973LUT/4467FF/21DSP/15RAMB18,
zero blackboxes, all seven source and option checks passed. Input DCP SHA256
`5165b1c7f2e641c6c747334cfcdc47c7244f9e8335d4174b622ec23f561c60c1`.
The original diagnostic route53502 and read-only DSP inventory87489 are running;
no new routed result exists at this checkpoint. The previous
175MHz setup result remains **-1.614ns**, not closed timing. A successful tool
exit alone cannot qualify CDC, external I/O, full receiver or deployment.

## Concurrent native/coarse/pilot counterevidence

The separate additive15MHz paired test's original175-v2 fails its positive
capture/FFT overlap or inventory gate. Parent inspected its raw terminal and
all52 public packet read lines: both reads of the26-word native packet match
the independent golden. The run reaches894scores/447map words/512pilot words,
with the2048-byte pilot binary independently reported equal to its frozen input.
Admission is at8589934602, capture start8589934991, lead388samples.

Diagnostic175-v3, original handle51228, fails the same unchanged gate and
identifies the sole missing term: capture/FFT overlap0. Other counts are
done1/admissions1/capture130/publicreads52/retainedstop1/compute-coarse-pilot842.
Actual capture ends120568.766ns, first FFT input123615.592ns: capture ends
3.046826us before the FFT starts, consistent with the real outer-bank fill.
The failed447 runs and strict overlap gate remain preserved.

Parent separately calculated an explicit520 profile from the unchanged raw
source using Python integers and Fraction ranking, not the fixed-correlator
oracle helper. Capture is[FIRST+488,FIRST+618),130samples wholly within existing
coarse support; winner-17, Re144077802, Im-27795799, Ex204670264, Eh1073742825.
The matching normalized score is approximately0.0979737: this is not the
injected PSS start447 and must not be called timing lock. Capture shifts4.866667us
later, predicting overlap while preserving source/coefficients/pilot bytes.
An explicit520 opt-in bench/oracle profile and one actual175/200 run each are
authorized after profile-specific golden/policy freeze. All overlap, admission,
retention-before-stop and numerical gates remain strict; predicted overlap is
not a substitute for observing it. The default447 profile remains unchanged.

This is concurrent arithmetic/ownership evidence only. True-PSS concurrent
capture and causal acquisition remain required. Neither static15MHz fixture
qualifies the guarded30/60MHz paired interface or live60MS/s RX.
