# Local guard observer scheduling — offline preparation only

The bounded offline gate passed **188 tests / 7.92 s**, original handle79779
exit0, Ruff PASS. No vendor simulator, waveform-query loader, FFT, synthesis or
route was invoked. Actual14041 remains a failed time-zero comparison, not an
accepted arithmetic or guard-equivalence run.

Tested code: FW `8130a750734c6fd9fc8cedb4131cfa9e56b71d22` /
HDL `62da6a39edb8e40e08d41cbb13ba04af7584842d`.

## Exact observer-only correction

The observer differs from frozen source
`ea16d902560799e4ddb694b8172fb689d6c2468378053ddad127655f9be7d368`
by exactly two substitutions:

```
compare(0);  ->  #0; compare(0);
compare(2);  ->  #0; compare(2);
```

These wait for the current Active-region input-alias propagation before comparing
in the Inactive region, without advancing simulation time or consuming pending
NBA assignments. Every positive/negative clock event, asynchronous reset event,
all155 state/output bits, case-inequality predicate, counters and existing +1ps
post checks remain. There is no startup, reset, valid, expected-fault or epoch mask.
The final receipt and the actual observer's hexadecimal diagnostics are unchanged.

Runtime8 modules, literal old/default guard bodies, full old and derived actual
stimulus, faults, all fatal checks, both119-bit product boundaries, vectors,
historical CSV expectation, real-core cycle limits, runner, diagnostic Tcl,
clocks and parameters are byte-identical to prepared-v3. The helper verifies a
whole-source inverse to the frozen original observer, not a predicate substring.
Rehashed changes to the waits, post delay, width, predicate, counters, reset edge,
reference or scheduling manifest are rejected. The original v2→v3 diagnostic-only
delta test remains against those immutable historical bundles.

## What the scheduling reproduction proves

The new standalone Icarus model instantiates either the accepted L1 guard or the
literal original RTL as the DUT, with the same actual-input→observer→literal-old
and omitted-default hierarchy. A selectable transparent procedural Active-region
copy of the ready input models a delta that Icarus can otherwise optimize away.
It is explicitly a scheduling abstraction, not a reconstruction of Xsim's kernel.

With unknown startup controls and ready=0 preceding the time-zero clock X→0
event, the old immediate observer fails in **both DUT controls**. Diagnostic-only
binary formatting in those generated negative-control copies identifies exactly
bit153 (`input_transport_ready`): actual0, original/defaultX. The corrected
observer passes both direct and explicit-copy variants for both DUTs.

Each healthy variant checks1,159 clock events before/after, five asynchronous
reset events, 579 independent NBA sentinels and512 ordered input words. It includes
bounded ready stalls, invalid metadata X/Z bubbles, and two X/Z reset sequences.
The sentinel requires an NBA-updated tag still old at #0 and changed at +1ps.
Independent counters require no clock/reset observation to be dropped.

Four directed corruptions exist before an edge and disappear only in NBA:
descriptor state, current-fault output, public data output, and descriptor state
at asynchronous reset. The corrected observer rejects all four for both DUT
controls at the pre phase. Deliberately bad post-only and +1ps-pre checker copies
miss all four, demonstrating that these are genuine one-edge witnesses rather
than persistent faults caught accidentally by a later check. These bad-control
PASS markers are not healthy observer acceptance.

Important limit: bit153 is **not the same reported nibble difference** as actual
14041. The vendor hex print differs in bits103:100 and3:0, without identifying
individual mixed-X bits. Thus the model proves a sufficient alias-ordering failure
mechanism and the proposed observation schedule; it does not prove the exact
vendor difference benign. No saved vendor WDB was queried in this stage. An
actual successor still must pass the complete unchanged suite and recorded-history
review; the offline result cannot substitute for it.

## Attempts retained

- Direct startup probe with known controls: no failure reproduced,
  `/tmp/starlink-local-schedule-probe-v1.6I6IO7`.
- Explicit-copy probe with known controls: no failure reproduced,
  `/tmp/starlink-local-schedule-alias-v1.WVRNl2`.
- Explicit-copy probe with unknown controls: old observer fails at time0,
  `/tmp/starlink-local-schedule-alias-v2.Nhr45s`.
- First full model gate: **19 PASS / 4 FAIL / 0.60 s**,
  `/tmp/starlink-local-schedule-offline-v1.a1WEI4`. The four deliberately bad
  +1ps-pre controls raced the independent count sample at exactly +2ps before
  fault injection. Sources and all failed outputs are retained. Only the new
  model's count sample moved to +3ps; actual +1ps checks were not changed.
- Corrected model gate: **23 PASS / 0.66 s**,
  `/tmp/starlink-local-schedule-offline-v2.W1bTYW`.
- Final combined gate: **188 PASS / 7.92 s**, original79779,
  `/tmp/starlink-local-schedule-final-v1.oMk0t0`, with raw pytest log, XML,
  generated negative sources, compile/simulation logs and binaries retained.

Final command uses sanitized repository Python, `-B -m pytest -q`, and exactly:
`tests/test_starlink_local_admission_actual_policy.py`
`tests/test_starlink_local_admission_schedule.py`.
The prior349 tests were not rerun merely for packaging.

Original actual22656 and14041 remain in separate unchanged failure archives:
`732dfbdd6e1e717a2416a2f3c34f3ef764582428b7bb35e3a4360d0a0e7b3998`
and `f6f47375fae3d0f72881808198e7e8d6c14b39b3ef51734e2ce5add036088d9f`.
Their original outcomes, absent results.json, source/IP receipts and WDB bytes are
not rewritten by this correction.

## New source-only bundle

Only after tests and source commits, L0/L1 prepared-v4 bundles were created under
`hdl/library/starlink_pss_acquisition/build`:

- L0 manifest `cd756b7305d97f4c4a63f8e8b49a23e0996365988e9de89080c64ce050a7546c`.
- L1 manifest `1717107b5be08b9ff72e7a224cbf20a1354ddd215270a7cd1923b62e12b5d858`.

Each freezes49 files,19 compiled sources,8 runtime modules, three explicitly
loaded Python runtime helpers and the policy/model/reference provenance. New
compiled source is not added: only the existing observer's two waits differ.
No project or launch receipt exists at this gate. Full-bench Icarus elaboration is
syntax-only with the vendor core absent; that binary is never executed.

Observer SHA `a8057de409efcbf19680595c20ce5c2cc7ae7213ff459f7dd7ed162dc7b46551`.
Runner SHA `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`.
L1 diagnostic SHA `260e9dc61259ca3c6901fc46ad0fbaf9994943f2c30e2fa1f8041d15960865c7`.

The smallest proposed next evaluation remains one separately authorized
L1/R1B1O1/175 actual run, not an L0 pair. It must retain all11 original terminals,
76 core jobs, the exact historical complete CSV, all19,456 ordered words per
transform stream,16,986 output-derived oracle-only scores, guard counters and
155-bit current/reset comparisons, plus actual diagnostic history inspection.
No execution is authorized by this report. D/S/CDC union, canonical promotion,
physical closure, scorer-RTL, continuous receiver and RF qualification remain
separate. The full coarse/native15/30/60/pilot objective is unchanged.
