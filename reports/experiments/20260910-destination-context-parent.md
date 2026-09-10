# Destination readiness: independent contextual proof PASS, RTL still pending

Root81304 terminates0: **15 tests PASS in2.64s**, with11 pinned source/policy/
report files unchanged before/after. This is a finite combinational proof using
literal source expressions and the complete original retained owner, not new
runtime RTL, a clocked controller proof or timing closure.

The last routed candidate still fails at-2.504ns. Its epoch-release path passes
through mailbox readiness, retained reservation, destination preflight and the
common fault/admission decision. This experiment asks whether independent owner
faults already present in the common aggregate permit a shorter parallel
destination check without changing detailed diagnostic reasons.

The proposed scalar destination selects output mailbox readiness for inverse
work, or product-bank readiness for forward work. The exact contextual candidate
uses that replacement only when fast_running is exactly1 and the owner's private
reserved bit is known0/1; otherwise it uses the entire original common aggregate.
Every other original root and all six original preflight reason bits remain.
The proposed owner-knownness interface is not present in runtime yet.

## Evidence and limits

The root reads the final helper, full SV proof, test file, pre-evaluation contract,
result report and original owner logic. The final proof replays98304 owner
input/state combinations and110 distinct consumed-output signatures, with
333056 aggregate checks including four-state reset, phase, preparing, mailbox
controls and summary-option values. Separate enumerations cover all256 two-bit
lease pairs,65536 eight-bit four-state reason patterns,13824 independent fault
root/reason/option cases and2916 conditional reduction lemma cases.

Owner state is assigned arbitrarily without clocking. This overapproximation
does not prove release/ACK sequences or reset/admission reachability. Factored
logical OR contexts cover simultaneous causes by reduction; this is not brute
force enumeration of every full top-module input vector. Simulation knownness
checks are not physical unknown-detection hardware.

The raw scalar simplification is rejected: a known running/ready bank with
private reserved=X and no other fault changes the original unknown fault to
clean0. The exact contextual fallback preserves it. Four executed mutants fail
at the equality assertion: dropped current-fault root, dropped sticky reasons,
omitted knownness fallback and incorrect reset fallback. Source-pin changes and
malformed proof receipts are also rejected.

Frozen proof hashes:

- helper: `62d49494e09ff3f19cbc09265ea9cd42de60a5a322bd18b3b2f2f872962eeffe`
- bench: `1d7960ab536a0f94ca7de438d6d6a6707e2ddb1f1520e471ce17b43dc8cd688a`
- tests: `afe3d48e83864685e0bb0b9c841afee247975ef2466ac1f5e006a377aae036f5`

Root evidence:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/bank-and-destination-parent.qnOqMzK4/destination`.
It contains independent copied inputs, before/after receipts, commands, JUnit,
all actual compile/simulation logs and result.json. The parent run.py launches
the independent59 bank tests concurrently with these15 tests, with150s outer
timeouts. Both finish normally; no vendor process is launched.

Next: an additive default-off runtime candidate with a read-only owner output,
strict whole-source inverses, unchanged state/release/reason equations and full
clocked/composed comparisons. No change to the frozen proof is required. Runtime
review and actual vendor qualification precede any physical comparison. The
bank-local identity candidate is independently progressing; their combination
is not assumed qualified by separate tests.

No radio/PPU operation, clock waiver, main merge or production HDL gitlink change.
