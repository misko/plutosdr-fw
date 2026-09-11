# Private inverse ACK retirement — isolated candidate, DO NOT MERGE

Parent FW `563614b87` / HDL `576eb8897`: whole held handoff, -1.868 ns WNS /
-565.807 ns TNS / 720 failing endpoints. Compare also to private certification
(-1.452 / -451.168 / 704) and guard facts (-1.340 / -463.636 / 821). No reference
is timing-closed or deployment-qualified.

## Runtime change and required safety contract

Add default-off `PRIVATE_ACK_RETIREMENT` to the result guard. Only the inverse
guard in certified-admission mode opts in. Its private awaiting-ACK bit may clear
when actual readiness arrives on a **known** same-edge idle fault. Original
public ACK/admission/publication and fault accounting remain literal. The
original mode still holds its bit in that case. The only intended difference is
private occupancy (and consequently internal busy) after the fault register has
latched known quarantine. This is not an early public ACK or permission to reuse.

When idle fault is X/Z, retain the original conditional's hold behavior. The
known-zero-or-one check imposes no binary-hardware fault qualification, but makes
simulation unknown handling explicit. Reject combining this option with the
substituted `USE_PHASE_INPUT_FAULT` contract: full inactive fault accounting is
required so every known idle fault is recorded on the same edge. A changed
private bit must never escape quarantine before common reset.

Whole top/guard source inverses check the limited delta. Historical whole-file
inverses now use SHA-pinned parents; live predicate tests and the new complete
inverse still cover current code. The actual FFT bench instantiates a guard with
the original ACK update and identical live inputs. Its outputs grant no control.
Compare ACK/admission/return data, validity, active state and full fault reasons.
An awaiting-bit difference is permitted only with candidate=0, original=1,
both protocol faults known one and public ACK/admission known zero.

Six new real-reader-ACK cases: current vendor fault, orphan raw output, orphan
status, fast reset, slow reset and healthy release. Fault cases must suppress
the public release on the exact readiness edge, retain quarantine for 100 clocks,
then recover after reset with 512 correct reads and one actual release. The
physical reader has already consumed its 512 words before these injections;
the test does not pretend those reads were cancelled retroactively.

## Frozen gates and initial tests

28 unit/preflight tests pass in 10.73 seconds. Eight focused tests pass in
0.13 seconds after adding real accounting coverage (five overlap the first run).
Transition table: 128 cases, exactly one permitted known-fault difference;
unknown/default behavior unchanged. Actual inactive guard: 16,384 four-state
combinations across seven fault/event inputs, with idle fault case-equal to the
full fault OR. Missing external accounting, incompatible phase contract and
three wrong retirement expressions are rejected.

Require all 64,512 actual FFT records unchanged, six service intervals unchanged,
complete regression pass, original-guard public equivalence and known quarantine
on every private difference. Route source-matched at unchanged 100/175 MHz
diagnostic clocks and compare WNS/TNS/failure count against all references.
The expanded bench's absolute timeout is 4 ms rather than 3 ms to accommodate
six extra recovery runs; per-context service limits and physical clocks are
unchanged. No new receiver features before timing closure.

Prepared inventory: `201ab2965aa0f271643d4302af0467359ba50b65ef8249a862ab519bb3ef55a8`.
Actual FFT passes in 211.39 seconds; source-matched synthesis passes in 96.13
seconds, both first attempts. All 64,512 numerical records match with identical
CSV `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service remains 3659/3659/4927/11727/3659/3659 clocks; the 11727-clock context
deliberately pauses its reader for 9000 clocks and is excluded from the
5215-clock diagnostic service bound.

The original guard witness passes 501,911 cycles. Exactly 306 observed cycles
have a private awaiting-bit difference, always under both guards' known sticky
quarantine with public ACK/admission zero. Public/diagnostic comparison remains
case-exact in these cycles too. All six new readiness-edge cases pass, each
finishing with 512 correct reads and one release after healthy completion or
fresh reset. The actual bank witness also passes 501,910 falling-edge state
checks. Its 75 first-word, 190 final-word, 115 replay, 25,078 valid/ready reader
and 21,950 stalled-reader counts are observations, not unique completed frames.
181 admission and 131 completion receipts include aborted work.

Synthesis DCP: `016f61a95632d0b7859145d8687ff9e6e3c29ab7e3077651d0644b5ff499454b`.
## Completed regression and route: improvement, not closure

514 combined regression tests pass in 74.65 seconds. Ten new audit controls
reject missing/duplicate cases, insufficient reference/quarantine coverage,
disabled public comparison and incomplete recovery. Actual FFT, synthesis,
route and unit/regression invocations all pass on their first run. Route takes
67.19 seconds; independent source/checkpoint/report audit passes.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification reference | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |
| Whole held handoff parent | -1.868 ns | -565.807 ns | 720 |
| Private inverse ACK retirement | -1.617 ns | -488.478 ns | 679 |

Compared with its parent: WNS improves 0.251 ns, TNS improves 77.329 ns and
41 fewer endpoints fail. Compared with private certification: 25 fewer failures,
but WNS is worse by 0.165 ns and TNS worse by 37.310 ns. **Retain both candidates;
do not call this an overall best reference, a timing pass or deployment firmware.**
679/13797 setup endpoints fail. Hold +0.057 ns and pulse +1.830 ns pass. All
8340 nets fully route with zero errors. Resources: 2771 LUT / 5666 FF / 21 DSP /
15 RAMB18, zero RAMB36. Diagnostic clocks and recipe are unchanged; no new
waivers. Five critical CDC findings, 208 warnings and 114/124 unconstrained
board I/O remain.

Worst path now ends at inverse guard input-count bit 7, from registered scheduler
phase through input metadata identity/checker and delivery qualification.
Eight levels, 7.276 ns data delay, 5.828 ns routing (80%). Next is another input
count bit (-1.577 ns). Private ACK retirement removes the prior worst endpoint
from this report's top position; it does not prove all ACK paths are closed.

Next inspect private input accounting versus certified delivery. Determine which
prequalification offer can safely advance only private count/completion state
on a fault edge while the same-edge full diagnostic quarantines any divergence.
Do not claim a private offer was delivered to the FFT, and do not change public
input valid, final qualification, diagnostics or reset/ownership gates without
separate proof. Verify healthy/unknown behavior and fault-edge quarantine against
the original guard, then rerun actual FFT and unchanged routing. Compare with
the private-certification reference and this candidate before promotion.

Routed DCP: `58ae66aa8d7bbed4c137c493f32b6b8b52a032d3b24060e7e48a4a67a536d45b`.
Evidence folders: `staged-privateack-{prepared,actual,synth,route}-v1` and
`staged-privateack-{unit,accounting,regression}-v1`, with XML receipts, under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

## End state remains unchanged

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC and full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s calibration and Ethernet/IIO qualification precede
`.18` reversible canary, then `.17` PPU Ethernet-only deployment with rollback.
Final gate: 300-second scan, 120 ms valid dwells and blind host GLRT comparison.
No radio, PPU, main or primary production HDL changes. The new HDL worktree
excludes historical evidence files via sparse checkout; no existing evidence or
other worktrees were removed.
