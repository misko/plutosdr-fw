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
Original route53502 completed exit0 at04:34:36 UTC. Its physical gate fails:
175setup-1.559ns/hold+0.071ns,TNS-518.092ns/553 failing endpoints;
100setup+1.851ns/hold+0.100ns. Routed1973LUT/4545FF/1045slices/21DSP/7.5BRAM,
all6668routable nets complete. Worst descriptor[51] to kernel history CE is
6.984ns (1.634logic/5.350route),9LUT levels through output-bank framing checks.
Routed DCP SHA256
`aa8ec6210d3e495ca39567bb3dd74eb276c06dbca247e13ac45f60fae060b955`.
The worst slack improves0.055ns, but same-clock failing endpoints increase
from501 to553 and TNS worsens; do not claim overall timing closure or better
quality from WNS alone. Parent read the raw terminal/receipt/top path, utilization
and route status. Synthesized DSP inventory87489 and routed inventory37187
both completed exit0. Parent rehashed both checkpoints unchanged and inspected
the actual routed DSP properties/cones. All four product DSP input-register
enables now exclude descriptor/metadata/current raw-checker startpoints; their
worst setup slacks are+0.708,+1.250,+1.241,+0.426ns. This establishes removal
of that measured enable-path problem, not closure of the entire design. Final
DSP AREG=1/BREG=0; the two sum primitives use MREG=1/PREG=0 after physical
optimization, so preliminary inference alone would have been misleading.
No physical retry is authorized.

Final physical/archive pins are FW `5c563826608397ba5783f3ce9d58ecd6f68ebbd5`
and HDL `ce6a885e60592a926c4c2d8b8c069ea45397b900`, with tested RTL unchanged.
Parent read `docs/starlink-payload-bubbles-physical-20260910.md` and independently
verified all70 physical-archive SHA256SUMS entries. These remain on the
separate completed-input-fence do-not-merge branch, not primary runtime.

Read-only next-cone review will examine phase separation: output-bank current
framing faults require an inverse-phase private write, while forward joiner
retirement requires forward phase. The sticky bank fault and global same-edge
reason/commit vetoes must remain. A source-level invariant is not a timing
exception; any proposed refactor needs its own exact-source tests before a
new physical trial. A successful tool exit alone cannot qualify CDC, external
I/O, full receiver or deployment.

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

The original520/175 run99570 now passes:319 fast-clock capture/FFT overlap
cycles,842 native-compute/coarse/pilot accept observations,130raw capture
samples,52exact public reads of the26-word packet retained across coarse stop,
894scores/447map words/2048pilot bytes. Parent inspected the raw terminal and
strict postprocessing receipts. The identical-source200 run62551 also passes:
366capture/FFT cycles,842compute/coarse/pilot observations and the same exact
packet/map/pilot counts. Both actual admissions have461samples of capture lead.
Parent inspected its raw terminal and independently ran all58 new policy tests:
58passed in2.99s. A later additive dependency audit must separately record six
package/transitive Python modules not copied in the original four-math-module
freeze; original manifests and run inputs must not be rewritten retroactively.
No RF or PSS-lock claim follows from this static later-window control.
