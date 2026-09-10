# Accepted high-rate offline cohort and new rounding-path measurement

## Primary integration: offline30 reference only

Parent read the complete783-line oracle,381-line tests, CLI and182-line report
at FWd3371d154 / HDLb49553c1. Independent replay:134 PASS in4.36s. The installed
CLI independently recomputed every frozen numerical artifact and source hash.
Parent checked all150 safe unique archive members,137 regular files, against
their original bytes; archive SHA256
`5439c4409fcb657090d672bfa83151ccabf6ebcf90986e9dc07ce225dedafdbc`.

The six additive FW files were merged at
`e5bd2ec0e3a6b2131af2c95630f4b545f10c2bbd`. Primary CLI verification of the same
unchanged cohort passed. No runtime, HDL gitlink, Linux driver, public profile,
radio or PPU changed. Full report:
[30 MS/s offline cohort](../../docs/starlink-high-rate-paired-offline-20260910.md).

The common raw source is8205 words, conditioned to4096 canonical samples:
7 full FFT blocks/3129 scores, original-rate132-tap native search with121
qualified tuples/exact zero-lag packet,512 supported pilot outputs. Pilot
coverage includes native capture and the two-block map envelope, not all
seven blocks. Neither actual30/60 integration nor source/command latency has
been measured. The earlier implicit60/shared admission remains forbidden.

Next high-rate work needs a new explicit public bank+STOP contract, including
DDC saturation and discontinuity health, actual high-word serialization,
immutable old profiles and real disabled-DDC startup. The frozen offline
producer must remain immutable when runtime sources change: verify it from
its archived source snapshot and independently bind the reviewed DUT delta.
Do not regenerate golden arithmetic merely to absorb a public ABI change.

After direct wrapper/PSMA identity-source review, parent authorized isolated
Stage A implementation/offline tests only: new30-upper bank+STOP ABI1.7,
capabilities0x7ff, DDC0x000f0203/delay7, explicit default-off bank selector and
exact pilot/shared/realtime/bank/STOP combination. Preserve all old profiles.
New-mode health includes0x77ff plus DDC discontinuity, coherent high words and
retained-map failure semantics. Actual FFT,60/lower admission, Linux edits,
receiver BD/build, physical or radio work are not authorized by this stage.
Return the driver delta proposal and module/offline evidence before advancing.

## Separate rounding candidate: real local physical improvement, not closure

Root created FW/HDL `codex/starlink-rx-only-do-not-merge-round-boundary` under
`/tmp/starlink-coarse-alternatives.Y3JzOI/round-boundary`. Runtime option remains
default-off. It decides saturation before rounding increment, removing the
wide carry-to-comparison dependency while keeping the entire sequential
pipeline literal. Independent subagent algebra review found no binary-value
error and identified test/compatibility limitations. Root preserved legacy
default width1, added invalid X/Z bubbles, source handshake bookkeeping and
final accepted/emitted/discarded accounting/drain. Four-state function equality
is NOT claimed for unknown arithmetic data.

Final standalone gate:23 PASS in11.74s, including3161728 width18 comparisons
against sign-magnitude Python math and independently frozen old RTL, ten
widths,6000 stress clocks/width, mutation and option guards. At width18:
2734 accepted =2645 emitted +89 reset/flush discarded, final outstanding0.

Both first A/B OOC routes completed with the identical175MHz clock and port
budgets. Original overflow path: -1.577ns setup,7.086ns delay,8 carry cells plus
4 LUTs. New overflow path: +2.229ns setup,3.380ns delay,3 LUTs and no carry.
Global setup moved -1.577 to +0.207ns;99 LUT/352 fabric FF became62/278,
with4 DSP unchanged. **Both still fail hold** (-0.646/-0.685ns,176 endpoints).
These are isolated product measurements, not bank/receiver timing passes.
No constraints were waived, no source edited during either run and no retry
was performed. The bank's authoritative measured setup remains -1.907ns.

Separate report:
`/tmp/starlink-coarse-alternatives.Y3JzOI/round-boundary/docs/starlink-round-boundary-study-20260910.md`.
Root artifact SHA256:
`7f3e9282f000d9c0c0c1606fb9b934d031086b0a34a552cb5e005ae9e258a5c0`.
This candidate is not merged into primary runtime. It still needs actual-core
bank/fault/ownership integration and physical remeasurement with the other
critical paths present.

## Other independent work

Parent independently replayed102 exact-control/legacy-inverse tests in21.74s
and checked315 archived hashes. The distributed fault/scratch candidates
remain isolated/default-off. Their next harness observes actual-core active
traffic against a self-driven frozen reference, not forced copies of DUT
internal signals. No new control-candidate physical pass exists.

Expired native request first175/200 simulations both failed before source or
request admission at9505ns. A separately authorized175 diagnostic preserved
the same failure predicate and proved the only failing operand was busy=1 in
the legitimate coefficient-energy preparation state, with the other18 no-work
operands0. A separate implicit-source_enable declaration warning/X value was
also retained. These failures establish no late-command result. Test-only
corrections are authorized: distinguish explicit coefficient preparation from
sample work, retain unconditional zero capture/result/fault checks, require
idle after configuration, and move the negative bench's source declaration
before first use. Offline review is required before fresh actual runs.

That correction is now reviewed at FWb07e0419 / HDL1ece302e: parent read the
complete source/test delta and report, independently replayed303 tests in9.91s
and checked all120 archive hashes (SHA256
`6ff880d76a446e7be15a8af94f40a8cc307fac7e76e28cfb58c9837468023615`).
One fresh175 and one200 actual run are authorized with unchanged numerical
and negative-event contracts, new output directories and retained original
handles. No corrected actual result is claimed by this review.

No radios were allocated or contacted. Full15/30/60 fine search, independent
2.5MS/s IIO pilot, causal120ms visits/eight targets/300s scanner, blind host
comparison, receiver timing/CDC/reset/IO/calibration and `.18` then Ethernet
PPU `.17` deployment all remain the unchanged objective.

## Follow-up: corrected actual evidence accepted; control pair launched

Both corrected late-command simulations completed exit0 at06:22:07/10 UTC,
175/200MHz respectively, without intervening source edits or retries. Parent
read the complete final report and independently verified every one of256
safe unique archive files, both complete115-source inventories, all13 pinned
Python runtime files/run,62 ordered public register values/run and512 pilot
ordinal/index/data tuples plus2048 bytes/run against the frozen contracts.
The exact scheduler lead was -136 samples: rejected/late1, capture/completion/
packet/IRQ0. Coarse894/map447 checks and later deliberate invalid-release and
reset quiescence gates passed. This is actual-generated-core simulation, not
physical hardware or RF evidence. Archive SHA256:
`61290438624552f8a3af9a0d733150f0dfd3ac5b06fe79fc1ecba39216348707`.

The additive expiry harness was merged into experimental primary HDL
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`: exactly three new test/helper files
relative to b49553c1, no runtime edits or deletion of existing map tests.
FW evidence21a404d8f was merged with all earlier failed attempts retained.
Primary regression original65080 completed303 PASS in12.34s. No firmware-main
merge, radio access, flash or PPU change occurred.

Parent also independently reran93 control-preparation/fast tests in15.91s
(50353 exit0), reviewed the final strict parameter/receipt delta, and verified
447 archived hashes. Two actual175 configurations were authorized and launched
06:35:55 UTC: baseline r0-d0-s0 handle60442 and combined r1-d1-s1 handle8914,
both extras1, frozen FW613b14e673 / HDL027a903f7d. The owning agent polls those
original handles; neither has a terminal result recorded here. No physical
trial, attribution modes or source changes are authorized by that launch.

Separate root rounding checkpoint inspection completed without DCP mutation.
Internal setup/hold moved -1.577/+0.084ns to +0.964/+0.103ns; all176 negative
hold endpoints in each isolated design launch at top-level ports. The old
physical log records37 registers pushed out of each sum DSP; new PREG1/PREG1
retention explains the74 fewer fabric FFs. Port holds are not waived and the
bank remains at its authoritative -1.907ns setup result. Separate immutable
audit archive SHA256:
`e86f7ca743bbc004bd3d57b5da08390752e7381f1f90b81cf985468bdd5af3e8`,
on round-boundary FW90fc402229 / HDLce9c863a. The runtime is unchanged.

An isolated standalone operand-register wrapper implementation/offline test
was authorized on a new operand-boundary worktree, based on those rounding
pins. It must explicitly add one no-stall token latency, capture both complex
operands and79 metadata bits, preserve exact default passthrough and prove
accepted-token arithmetic/conservation/reset/flush semantics. Logical added
state is4D+80 bits (152 at D18). No bank integration, physical mapping claim,
actual FFT or radio operation is authorized for that prototype yet.

Stage A30 interface review found that its new parameter guards used logical
inequality, which can miss X/Z values. The isolated agent is requested to
harden only the new bank admission with case inequality and literal-instance
unknown-parameter tests, retaining the initial310-pass receipt and every old
numerical/legacy contract. Stage A is not yet promoted or actual-FFT-qualified.

### First control pair: failed, not accepted

Both original handles60442/8914 subsequently completed exit1, approximately
4m10s wall each. Baseline and combined cases both stopped in epoch11 on
`EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH`, at1198594347644fs and
1200640062032fs respectively. No original or extra terminal PASS receipt was
reached; partial traces cannot satisfy the full original CSV hash gate. Parent
read both raw failure sites and independently found the baseline candidate
and reference partial CSVs byte-identical up to the stop. That narrower trace
equality does not explain or waive the broader217-field mismatch.

Epoch11 is the original missing-forward-status / held-final-readiness test,
not an extra epoch. Because the unmodified-option baseline also fails, the
new observation/reference composition must be investigated alongside the RTL;
this alone does not prove that either the observer or candidate is at fault.
Read-only waveform/source diagnosis is authorized. No rerun, changed compare
scope, altered CSV hash, physical build or runtime promotion is authorized by
this failure. Both original outputs and frozen sources remain preserved.

## Stage A guard repair and operand wrapper accepted offline

Parent read both complete Stage A benches (582 lines), the full wrapper and
controller delta, all new tests, strict inverse and source collector. The
new bank admission uses case inequality and rejects literal X/Z in every
required field, while old guards/default behavior remain unchanged. Independent
parent43177 completed340 tests in10.44s. Parent checked all1474 receipt hashes,
1475 safe regular archive files and the96-file source signature, then reran
the immutable snapshot producer: all51 original numeric artifacts matched.
Isolated FW6d2252552 / HDLe2a8773b is preserved on the remote high-rate branch;
primary runtime is not promoted. Archive SHA256:
`63bd842f5531b137e14c0a78b3fd2ac8b57be2ceaed01b424e58e9152621a858`.

The next approved implementation is an additive healthy30-upper actual-harness
preparation only: real public PSMA1.7 bank175, native132/injection0/DSP1, PIL1,
447x2 map and the same frozen raw samples. No old15 helper or golden changes.
The15 bench's packet-before-coarse-STOP ordering cannot be assumed at30:
capture/compute must survive coarse STOP, retaining the map until later native
publication/read/release. The129 raw lags times132 taps give17028 correlation
issue cycles, not a full service bound. Derive a conservative engine/reducer/
public-read bound before fixing an independently generated continuation.

The actual30 conditioner disables when both coarse and512-sample PIL1 stop.
Consequently, a reduced STOP run must check every independently modeled active
canonical/FFT prefix without claiming all4096 canonical outputs or seven full
jobs. Keep exact894 admitted scores/447 map words,260 raw capture samples,
129 raw/121 qualified tuples,26 packet words and512 pilot words. Two real
disabled-DDC prime beats precede the untouched8205-word raw cohort; no pause
may interrupt admitted native capture. Static known-center timing is not a
causal candidate handoff or live accuracy claim. Actual FFT launch,343 profile,
negative epochs, Linux/BD and physical/radio work still require later gates.

Parent also read the complete standalone operand wrapper/bench/Python suite
and independently reran29 new tests (68767 exit0,1.93s). The agent's52-test
combined run includes23 retained rounding/product tests. All268 safe archive
file hashes independently match, SHA256
`10213e850e4958d2f7b5e041b62cd4461874eceeb84f150b1bf2ae4bda089176`.
Offline pins FW375c5e6f / HDL0aeb4c09 preserve the arithmetic hash unchanged.
The explicit one-cycle extra latency,152 logical added bits at D18 and
insertion-time overflow contract are accepted only for this isolated slice.
Preparation of an identical-budget A/B175MHz physical runner is authorized;
no synthesis or route has launched. Real DSP input mapping, bank fault/ownership
integration and receiver timing remain unproven.

Both failed control runs are preserved at FW5fe9ac36 / HDL29fa754a. Parent read
the report and checked all102 archive hashes. Read-only WDB inspection found
zero recoverable candidate/reference field pairs among the217 compared fields;
names exist but the original waveform did not log their values. A new baseline
diagnostic preparation may print exact mismatching fields immediately before
the same unchanged fatal/2ps observation. No diagnostic rerun is authorized yet.

## Diagnostic outcome and next source-specific preparation

The subsequent observation-only preparation passed50 independent parent tests
(25748,2.16s); parent verified62 archived hashes before authorizing exactly one
baseline diagnostic, frozen FWc13a04e539 / HDLf43cdcf9. Original handle69434
completed exit1 at the same1198594347644fs failure point. Parent read its raw
terminal: only `dut.core_status_data` differs among217 fields, candidate
`xx100101` versus reference `00000101`; original and freshly evaluated exact
comparisons both fail. Bit5 is1 as well as bits7:6 being unknown, so this is
not explained merely as unknown padding. All other216 fields agree. Original
and diagnostic partial CSVs remain byte-identical; no complete-run CSV or
terminal PASS is claimed.

Read-only saved-waveform analysis records the old independent guard's public
valid high at the fatal instant. Together with its literal current-status
veto and equality of the two status-valid fields, this implies both raw status
valids were0. This is a source-backed inference, not direct capture of those
unlogged raw aliases. Parent read the runtime guard: every status-data consumer
is gated by status valid, including all three reserved bits and the five-bit
exponent. The protected mixed-language vendor driver after force/release is
not proven. No status-bit mask or runtime change has been approved.

The next requested proposal is narrowly protocol-qualified observation of
this one payload: retain unconditional status-valid and all216 other fields,
retain all8 payload bits whenever either valid is not exactly0, and separately
record invalid-only differences. It must preserve valid reserved-bit/exponent
fault tests, all numerical/CSV/public reason gates and original raw mismatch
evidence. At this checkpoint that is a proposal, not an implemented comparison
change or authorized actual rerun.

## Operand physical preparation and first launch failure

Parent read the complete physical runner/XDC/probe/policy and independently
repeated57 tests (61687,2.72s), then verified953 archived hashes. Preparation
FW184223801 / HDL7d4efdb3 froze six sources, fixed D18/ROUND1/175MHz and changed
only REGISTER_OPERANDS between the two arms. Archive SHA256:
`a2567f8255033677990d81db22be292a85aed9686904bd93ed8759fd34fc13be`.

The two authorized first runs19364/49440 both terminated exit1 before synthesis
at07:08:40 UTC. Parent checked both compile logs and receipts. System Icarus
inherited Vivado's incompatible `libstdc++.so.6` and could not find
`GLIBCXX_3.4.32`; both source-integrity checks stayed clean. There are no DSP,
resource, placement or timing results from these runs. The failure archive is
preserved on operand FW83d17873 / unchanged HDL7d4efdb3, SHA256
`95f9a5df380fe98eeb0aeff6e7536ec46973192a3fb4aee81f587fd7f5bd9514`.

A subprocess-only correction is authorized for implementation/offline testing:
remove LD_LIBRARY_PATH only for Icarus compiler/runtime children, preserving
the parent Vivado environment and all RTL/constraints/probe rejection gates.
New source freeze and parent review are required before any physical rerun.
The original failures remain retained. Parent's initial preflight pytest temp
directory was removed by shared pytest retention; its equivalent agent-owned
raw failures are archived, not substituted for the missing parent raw files.
Future tests use unique explicit basetemp directories and retained logs.

## Native30 service budget independently checked

Parent read the complete new standalone native30 bench/helpers/tests and
repeated3 tests (58296,1.05s). With the unchanged public native engine/reducer,
both the complete8205-sample input and early source-disable case publish in
19911 engine cycles after capture and finish indexed packet reads/release in
20700 cycles. All260 samples,129 raw/121 qualified tuples and52 ordered packet
reads match the frozen independent cohort. Maximum direct AXI transaction
latency is7 cycles.

The predeclared healthy configured-job bound is22404 derived cycles,24000 for
publication and28000 including bounded direct AXI readout. A new4096-raw-sample
continuation leaves31740 engine cycles after capture, with3740 cycles margin.
This is not an ARM/network arbitration bound or causal acquisition proof.
The additive combined30 harness remains offline-only pending full source and
provenance review; no actual FFT, physical receiver, radio or PPU work is
authorized by this budget result. Full15/30/60 deployment gates are unchanged.
