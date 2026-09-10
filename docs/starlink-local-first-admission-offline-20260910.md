# Local first-admission CE — offline equivalence only

The default-off candidate matched the original guard's complete compared outputs
and private state in all four CHECK_INPUT_BLOCK_IDENTITY / BALANCED_IDENTITY_EQ
configurations. Final **349 tests PASS / 52.60 s**, Ruff PASS. No actual FFT,
synthesis, placement, routing or receiver integration was performed for this change.

Tested code: FW `40d8224cf4deffa245d3ff7860b8289d9d47b532` /
HDL `461eda9fd2bf67a975f6016f06a8be789af9f077`. Original guard and arithmetic probe,
all previous helpers/benches and every earlier freeze remain unchanged. The strict
inverse reference is HDL `5b68bb8b488a886c3861537eaf9643ec940003e0`.

## Smallest cut and unchanged contract

The failed arithmetic route's worst 175 MHz path was expected_position[1] to
descriptor[2]/CE, −1.341 ns: 6.766 ns data delay, including 4.903 ns routing.
The original guard loads job_started and descriptor under
`!protocol_fault && !fault_now && job_start`. This puts current metadata checks
on a shared enable for 71 stored bits.

Only the additive candidate's first-admission load uses:

```
!protocol_fault && job_start && !job_started
```

With job_started=0, slot_open is closed, so current framing/delivery/duplicate
events cannot veto first capture. With job_started=1, another start is a duplicate
and cannot overwrite the descriptor. The test compares procedural four-state
behavior, not just a two-state simplification.

All remaining input_started, input_complete, fault_reasons, expected_position,
metadata/position/TLAST comparisons, demand checks, current faults and certified
beat/completion equations remain literal. Result-guard and publication/commit
connections are unchanged. The change adds **zero state bits and zero pipeline
cycles**: it changes the enable expression for existing 70+1 bits, not their
observed values. The guard still has 85 logical stored bits. Physical timing or
mapped area effects have not been measured.

The new guard module is `starlink_pss_realtime_input_guard_local_admission`; the
derived top is `starlink_pss_fft_bank_owned_local_admission_probe`. Both append
LOCAL_FIRST_ADMISSION=0 after existing positional parameters. Existing canonical
modules/default callers are untouched. The derived top forwards the option only
to its input guard; B/O/R defaults and product arithmetic are unchanged. Eventual
production promotion must collapse a reviewed change into canonical code rather
than accumulating experiment variants.

## Exact offline witnesses

Each configuration compares the literal original guard, new default-off guard,
and option1 guard before/after clock edges. The compared tuple includes every
output plus descriptor, job_started, input_started, expected_position, fault state,
slot eligibility and all current certificate/metadata fields. No invalid payload,
fault epoch or private state is masked.

Per configuration:

- 21,113 cycles; 14,187 reachable-stream comparisons.
- Three healthy 512-word jobs with bounded ready stalls and invalid X bubbles;
  post-completion N+1 presentation cannot overwrite N.
- All 70 walking-one descriptor captures.
- 420 metadata probes: all 70 bits × forward/inverse identities × flip/X/Z.
- 54 position probes: all nine bits × both identities × flip/X/Z.
- Five duplicate-start probes, including a current ready/valid beat, plus TLAST,
  realtime-demand, reset/recovery, and four data-X/Z probes.
- 16,384 explicitly arbitrary-state snapshots / 65,536 comparisons. Seven
  selected controls take every 0/1/X/Z combination; remaining inputs are
  deterministic representative patterns, not an exhaustive formal state proof.

Arbitrary snapshots are separately labeled, never counted as healthy reachable
traffic. X/Z values retain the original four-state behavior; an unknown-valued
original reason is not relabeled as a known sticky fault. CHECK_IDENTITY=0 retains
the original intentional identity bypass.

Eleven semantic mutants fail the independent old-source shadow: missing start,
missing first-start, missing protocol gate (specifically an arbitrary-state
witness), wrong enable, zero/direction/start/exponent capture corruption, removed
identity check, removed current duplicate certificate veto, and removed sticky
fault update. Strict whole-source inverses additionally reject omitted/duplicated
anchors. Parameter tests verify defaults, positional prefixes, invalid/X/Z options,
and actual derived-top forwarding plus its omission mutant.

Top parameter tests use Icarus's missing-module syntax mode with no FFT instance
implementation or traffic. They are explicitly marked SYNTAX_PARAMETER_ONLY;
they are not actual-core numeric or integration evidence.

## Retained attempts and final regression

Initial dedicated 33-test run: original handle 19618, exit 0, 4.15 s,
`/tmp/starlink-local-admission-offline-v1.7A2AgM`. It predates the added walking-one
descriptor loop; its generated source, compilation and simulation receipts remain
retained. No failing actual run exists for this experiment. Initial lint and one
atomic patch-anchor rejection are tool-transcript diagnostics, not archived test
failures.

Final original handle 91410: 349 PASS / 52.60 s, exit 0,
`/tmp/starlink-local-admission-final-v1.GQf9OB` (logs/XML/cases/Ruff retained).
The repository venv Python runs with `-B`; the exact suite adds
`tests/test_starlink_local_admission.py` to the previous 316-test OOC/arithmetic/
monitor/payload/retirement/archive suite. The new source freeze and archive record
all source identities, original references, complete test receipts, and explicitly
excluded large duplicate reconstruction copies/symlink references.

## Read-only combination recommendation and next gate

First qualify this local CE in the current arithmetic baseline alone. No D/S/CDC
combination is included. Registered eligibility would add control state and could
change admission latency; speculative descriptor scratch would change 70 private
idle bits. Neither is needed for this exact local-load cut.

A later minimal union can start from the reviewed control actual freeze
`8e9251fe06e41917e9e0b5ebceef36db444bc39770efe7acb940dbfcc4ed7906`
(tested RTL `ae50b1889fd10cd762fb60266aecbb7c163e1d1a`) and retain its D/S top,
joiner and kernel changes, replacing only spectrum_product with the existing
operand wrapper/arithmetic core. Preserve PRIVATE_PAYLOAD_BUBBLES, held overflow,
all raw/current/late veto connections and the complete original fault suite.
Compare same-D/S B0/O0 and B1/O1; do not silently shift whole-chain expectations.
The newer PER_CAUSE_FAULT_CDC option must use its own separately qualified freeze,
not be imported or enabled merely because it is present in a live worktree.

Retain the control observer's narrowly reviewed both-status-valid-exactly-zero
exception separately from unconditional 119-bit product comparisons; never label
that observer as original raw217 equality. No combination has been implemented.
Actual-equivalence preparation is the next separately authorized gate, followed
by source-specific execution and physical review. Full 15/30/60 coarse/native-fine,
2.5 MS/s pilot, .18-before-.17 and eight-target / 120 ms / 300 s goals remain open.
