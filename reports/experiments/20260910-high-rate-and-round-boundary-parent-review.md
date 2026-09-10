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

## Corrected operand A/B routed: mapping proven, not bank closure

Parent reviewed the subprocess-only delta and independently repeated60 tests
(6403,2.82s), retaining `/tmp/starlink-operand-env-parent.6WORFY` with explicit
basetemp/log/XML. Both child tools omit LD_LIBRARY_PATH while the parent keeps
it; inverse-diff verifies that only the two exec prefixes changed. All six live
hashes and archive SHA match the frozen report at operand FW881a838570 /
HDLf7345ab655. Preparation archive SHA256:
`19bea65015daa7e7f0c2528b83da70ec75030e3011f58a9436a76b60cdb9a533`.

Exactly two new source-frozen v2 physical runs were authorized. Original2548
(REGISTER0) and30333 (REGISTER1) completed exit0 at07:23:10/11 UTC. Parent read
the generated synthesis and route inventories, timing text, CE drivers and
route status, and verified all six synth/opt/route checkpoint hashes. Results
are isolated at the same175MHz constraints, D18 and ROUND1:

| Measurement | REGISTER0 | REGISTER1 |
| --- | ---: | ---: |
| DSPs; AREG/BREG on each of four | 4;0/0 | 4;1/1 |
| Routed LUTs / fabric FFs | 62 /278 | 59 /358 |
| All-path setup slack, ns | +0.207 | +0.085 |
| Internal setup slack, ns | +0.964 | +0.441 |
| All-path hold slack, ns | -0.685 | -0.685 |
| Internal hold slack, ns | +0.103 | +0.152 |
| Negative hold endpoints, all from top ports | 176 | 272 |
| Fully routed nets / routing errors | 398 /0 | 494 /0 |

The extra operand state is absorbed into DSP input registers;80 extra fabric
FFs hold metadata/valid. Routed A2/B2 clock enables connect to the registered
operand payload enable; A1/B1 are tied low for the one-register configuration.
MREG/PREG configuration stays unchanged. This proves the intended input-register
mapping in isolation, not improved bank timing: isolated setup margin actually
decreases, and both designs still fail all-path hold. The OOC missing-partition-
pin-location warnings and top-port timing limitations are retained, not waived.
Neither arm includes the actual upstream kernel BRAM or complete receiver.

Route DCP SHA256 REGISTER0:
`f1288c1f9d439614840f94df9bd2d5306dee7fa7ea1b8e78d48538b51272c5b1`;
REGISTER1:
`f5e6ecba7d57d5ea6963a90e8f1ec3fa353ccca924dc0086c854db5fffd893e2`.
Full measurement directories remain under operand-boundary
`hdl/library/starlink_pss_acquisition/build/operand-route-{0,1}-v2`.

Next is a source-specific bank integration proposal, not a receiver route or
runtime promotion. Preserve the tested dec20 forward-retirement baseline,
including its PRIVATE_PAYLOAD_BUBBLES parameter: the older standalone arithmetic
must not overwrite that implementation. Port only the reviewed rounding choice
and add the operand wrapper with explicit latency. Preserve the bank's held
`output_overflow` current/sticky/publication vetoes (not just overflow_pulse),
then requalify owned final words, reset/flush and delayed-fault behavior before
any bank physical run. The separate qualified-status observer is now authorized
for offline implementation only, retaining its original raw217 witness and all
other216 exact fields; no actual control retry is authorized yet.

FW/HDL operand preparation881a838570/f7345ab655 and diagnostic evidence
f98abdb333/0c1a23a701 have been pushed to their respective experimental branches.
Parent independently verified all57 diagnostic archive entries. No primary
runtime, firmware main, PPU or radio change occurred.

## Next actual checks admitted after independent review

The operand v2 report/evidence is committed and pushed at FWbd668d21c /
unchanged HDLf7345ab655. Parent independently verified all90 safe unique
archive members, including the previously checked six checkpoints. Archive
SHA256 is `573b139c5a1739e653edb90730b6f1333cc365ddb705f4d3222f8d77e015b50c`.
The exact printed warning count is103 per arm:100 Route35-198, one35-426,
one35-328 and one Synth8-7080. Those OOC limits and failed holds remain open.

An isolated offline bank arithmetic port is now authorized in
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic`, branch
`codex/starlink-rx-only-do-not-merge-bank-arithmetic`, based on exact
FWbda25bb5 / HDLdec20d637. Preserve original bank, core and legacy benches.
The candidate is an additive core derived by strict inverse from dec20 plus
the reviewed rounding option, compatible operand wrapper and a separately
named bank test top. Parent reviewed the initial exact deltas and wrapper:
registered private bubbles may update only unowned numeric payload; occupied
stalled tokens and metadata remain protected. Original sequential core and
all held-overflow current/sticky/publication connections remain literal.
No actual FFT or physical build is authorized for that new integration yet.

### Status-qualified control observer

Parent read the complete new preparation, tests and expanded real-guard
bench. Independent94648 completed29 tests in13.02s (23 new plus six retained
diagnostic tests), with unique evidence at
`/tmp/starlink-status-qualified-parent.Uzqln8`. Agent15112 completed73 tests
in14.02s, including the unchanged50 preparation/diagnostic tests. The expanded
guard suite proves reached phase states, matching/bad status coincident with
an output, and ready-high awaited ACK fault attempts; all omitted-veto mutants
fail. This is synthetic guard-interface testing, not vendor execution.

Parent verified all248 offline archive hashes and the exact prepared manifest
`36e44321ea694ee324f12613a54d0758219a62c7f9edd73b0106a45f6e70dd09`.
The runner remains `496a3ed4a2b55d494a22fd78f64b4a68580d923b398f5282e31145dc6a7951b0`.
Final offline evidence FW6395b6573 / HDLb4179711 is pushed. Exactly one baseline
R0/D0/S0/extras1/175/QUICK0 actual run was authorized on the frozen preparation,
original handle8757 owned by the control agent. No terminal outcome is recorded
at this checkpoint. All old numerical/full-CSV/extra-epoch gates and the new
independent qualified-observation receipt audit are required. The original
raw217 failure is retained and can never be relabeled as this contract's pass.

### First combined30-upper actual run

Parent read the entire paired top, native/source/FFT ledgers, standalone module
probe, helper, runner, parser/policy tests and final205-line report. Independent
55422 completed91 new harness/budget tests in9.01s; retained unique directory
`/tmp/starlink-highrate-harness-parent.jceqP8`. The real non-FFT module probe
again produced7250 enabled raw /3618 canonical /512 selected pilot samples,
19911 native publication cycles and20700 through public release. Agent's full
490 tests pass and the original51 numerical artifacts rederive unchanged.

Parent independently checked all358 prelaunch file hashes and95 live source
hashes, plus1326 portable archive hashes /1327 safe unique regular members.
The frozen source signature is
`413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31`;
bundle receipt SHA256
`2d410bc8a7984425751a527725e8f43c8406596b23f610e904199d1524863da5`;
portable archive SHA256
`47e74d2ca0ab54337c178806bc0c8b1027ed1531becb6e5a0a91b9d2e76df39f`.
FW6a99d1d538 / HDL446a8617 is committed and pushed. Its runtime is unchanged
beyond the earlier reviewed StageA; all new harness files are additive.

The first vendor launch failed before Tcl/project creation because the parent
LD_LIBRARY_PATH was unset and libtinfo.so.5 could not load. The launcher returned
0 despite that failure; this is not a simulation success. Exact stderr/command
are preserved in `main-high-rate30-bank175-447-v1.initialization-failure.json`,
SHA256 `223087f01f9fb9b68c75451fddeba62939c0b0adc44293e543baa119f26a59eb`.
Parent checked the receipt and installed SuSE compatibility library, then
authorized one new v2 launch using the established explicit environment:
`env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE /opt/Xilinx/Vivado/2022.2/bin/vivado`.
The independent Python verifier still clears vendor overrides only in its own
subprocess. No runner, RTL, fixture, profile or acceptance gate was changed.

Original57213 owns the environment-corrected actual run at
`/tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2`.
No terminal outcome is recorded here. The agent must consume that original
handle to completion; no timeout-based restart, source edit or tail extension.
This is healthy30-upper/175/447x2 only, not causal native scheduling,343/negative
coverage, hardware timing,60MS/s, radio calibration, live lock or deployment.
The complete original release objective remains unchanged and unfinished.

## Combined30 actual PASS; control extra epoch still FAIL

Original57213 subsequently completed exit0. Parent read the actual raw terminal,
reran both frozen bundle and result verifiers successfully, and verified the
full636-file generated-run inventory. The actual30 test checked894 exact
visible/admitted scores,447 map words,260 original-raw capture samples,
129 raw/121 qualified tuples,52 public native packet reads and512 pilot
samples/2048 bytes. Forward input/output/product and inverse input each had
1536 checked words;1024 inverse outputs were observed. This does not claim a
third completed inverse output or all seven stored fixture blocks.

Native publication took19910 engine cycles; reads/release completed in20700,
maximum direct AXI transaction8 cycles. The predeclared24000/28000 limits and
4096-sample tail were unchanged. Actual admission raw17179869201 had lead926.
STOP occurred at source4946 with native busy; native release at8991 preserved
the complete map, then map release at9000 preceded source exhaustion12303.
Observed overlap:273 native-capture/FFT-consumption beats,6433 compute/coarse+
pilot clocks,13219 compute-after-STOP clocks and43723 bank-quiescent fast clocks.
The real enabled-prefix ledger matched7250 raw/3618 canonical outputs.

Simulation endpoint453870ns and18.960s reported xsim CPU are host simulation
measurements, not FPGA/RF timing accuracy. Raw result summary is
`/tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2/run_summary.md`.
Simulation log SHA256:
`3fcb4f1b86a102421b8fd0f42b1e0885023782b4325303d599091942f67b47db`;
native raw tuple SHA256:
`1d16a0259f13a5a4ee914896c20449c9028bb79edd6a55253ae273496f908f8c`;
pilot bytes SHA256:
`f461fa6399c6163d462835310bb18aeb431cec4153225c385cd4e7b79c5282ca`.
The next authorized isolated work is result archival and offline preparation of
the already-golden343x2 geometry and a late-native-command negative at30.
No new actual run, runtime promotion or60 profile is authorized by this result.

Original control8757 completed exit1 at1924511525797fs, epoch54, in the
unchanged reference-bench `FORWARD_ACTUAL_JOIN_INPUT_MISMATCH` assertion.
Both original main CSVs are complete and independently retain historical
SHA256 `b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d`.
The original terminal blocks printed before extra epochs; there is still no
complete extra-epoch, qualified-observer or exact-control terminal PASS.
The29 invalid-status-only observations directly log both valid bits0. In this
run the candidate raw byte is11100101 versus00000101; the earlier strict
diagnostic's xx100101 pattern remains separately retained, not rewritten.

The failure occurs in newly added stimulus after the original suite. The
kind1 sequence returns from three ticks at posedge+1ps, then drives a vendor
fault/releases readiness at the same simulation instant as the old checker.
This is a source-backed race hypothesis pending saved-waveform confirmation,
not permission to disable or delay an assertion. Read-only diagnosis and a
proposal to move only added stimulus away from that sample boundary are in
scope; no source correction or actual retry is authorized yet. The complete
bank setup result remains-1.907ns, and no radio or PPU operation occurred.

Subsequent read-only saved-waveform inspection confirms extra_kind1/epoch54
at the failure; the partial extra CSV has three held no-output rows. The exact
relative process execution order remains unproven. Offline preparation of a
new following-negedge drive for only the added fault kinds0/1 is now authorized,
with still-held-final/ownership assertions before injection and all original
checker delays, current-veto/sticky checks and reset kinds2/3 unchanged.
No actual control retry is authorized by that offline correction scope.

Actual30 result evidence is committed/pushed at FW94de11b912 / unchanged
HDL446a8617. Parent verified all379 portable hashes /380 safe unique members,
archive SHA256
`229cd4500d3fff062c2fe8a091567f54298db98b76d962193944e5820dbf5454`.
The complete original636-file run is retained separately; the portable archive
omits duplicate generated executables and default waveform, not source or
numerical evidence. No receiver runtime or radio changes were promoted.

## Bank arithmetic independently qualified offline; actual preparation next

Parent reviewed the complete additive arithmetic implementation, both benches,
policy and final report at isolated FW5235285a60 / HDL41e539e768. Independent
repetition of the same suite passed101 tests in14.76s (original46097 exit0),
retained at `/tmp/starlink-bank-arithmetic-parent.USIztK` with unique basetemp,
raw log and XML. This includes65 new tests and36 unchanged regressions.
Parent also checked all31 frozen live source hashes and all5850 safe unique
regular archive members, SHA256
`08c2720c9f7d639548836427d079f5c720ecb64c60bf5f3feb8f203b11dee316`.

The new core/top are additive and strictly invertible to dec20, including
private-bubble behavior and held-overflow publication vetoes. The operand
stage adds one token of capacity and one no-stall clock (2 to3); numerical,
metadata, stalls, reset/flush and mutation checks pass. The bank ownership
tests use an explicitly synthetic zero-frame FFT interface: this evidence
does not prove vendor arithmetic, throughput, DSP mapping or bank timing.

The next authorized scope is OFFLINE preparation of an actual-generated-FFT
comparison, preserving original numerical/fault checks and rejecting the
synthetic interface in the actual source closure. Baseline and candidate
parameter identities, latency-sensitive checks, source/oracle closure and
cycle bounds must be frozen before launch. No actual FFT or physical launch
is authorized by this checkpoint. Primary runtime remains unchanged.

Parent independently verified all64 files of the control8757 failure archive.
The first offline fault-edge correction is also retained:7 tests passed and5
failed. Blindly waiting for the next falling edge can permit an intervening
commit when kind0 qualification already arrives in the low clock phase.
The next offline correction must handle that phase explicitly, reject unknown
phase, preserve kind1's three held positive edges and leave every original
checker unchanged. Both declared provider phases must be exercised before
any actual retry. This is test-stimulus work, not a runtime timing fix.

Actual30 healthy447 remains the verified positive result. Separate343 and
late-native30 cases are being prepared without changing its goldens. Full
bank setup remains-1.907ns;60 integration, full receiver timing/IO/CDC, RX
calibration, .18 canary and .17 Ethernet deployment remain required.

## Phase-aware actual retry and additional30 case qualification

The final phase-aware correction preserves every original checker and passes
53 independently repeated tests in13.49s, original81158 exit0, retained at
`/tmp/starlink-extra-edge-final-parent.U6Xc8O`. Additive provider witnesses
confirm exactly one qualification edge in each declared clock phase. Parent
read the final report and verified all540 offline-archive hashes, manifest
`a268fbd0350165c92fa2cae47ad7f24faa8a6c734f8fe57027ad3741f505469e`.
Tested source FW48b88f6786 / HDL12ce2854b3; report-only pins FWc9e191f898 /
HDLbed131df57. The runtime remains ae50; no arithmetic/control RTL was changed.

One source-specific actual baseline was authorized and launched at08:16:56UTC,
agent-owned original22816, in
`/tmp/starlink-completed-input.5EaJuD/extra-edge-prepared-v1`.
Its freeze hash is8efa2657fd43d4c7d2804d90abf9aa169fb8d916136ee681d38d4b533885ad92.
R0/D0/S0/extras1/175/QUICK0, unchanged runner496a3ed4, explicit SuSE parent
Vivado2022.2 environment and two threads. No terminal result yet. Both the
unchanged runner gates and the independent frozen qualified-observer receipt
audit are required; no original raw217 PASS is inferred. No candidate,
attribution or physical retry is authorized by this baseline launch.

Additional30 healthy343 and late447 cases are now frozen with104 sources:
original95 byte-identical plus nine additive files. Parent reviewed every new
file, strict whole-source inverses, geometry-specific816 slow-output minimum,
config-qualified continuous late/no-work guards and context-specific result
verifiers. Independent repetition passed253 tests in18.91s (162 new plus91
unchanged harness/native-budget tests), original9587 exit0, retained at
`/tmp/starlink-highrate-cases-parent.4zVDl8`. Agent full regression passes652.
Parent independently verified all515/518 bundle files and104 live sources;
shared signature b9d4d306fd9665133e36dc21e24125bce9ac7a6b3b34ed335b45fd5e2ba9ab09.
Healthy343 bundle SHA256:
`bbec5b49d80caf3ec50b6d595e33e7cf62d4ca18e665caa1573099e90ad99bd7`;
late447 bundle SHA256:
`9cfded42cd006d0524531dc36739461d86d8612c908e55810e81b4c08fa566ae`.
One actual healthy343 run is authorized after source/evidence commits; actual
late447 remains pending separate authorization. All original447 goldens, runtime,
24000/28000 native limits and4096-sample continuation remain unchanged.

## Two actual-core results independently verified

Control baseline original22816 completed exit0, Vivado exit08:22:56UTC.
Parent independently executed the frozen Tcl receipt procedure and qualified
observer validator, and rechecked the entire input freeze. Both complete
original CSVs retain historical b0d60e80...; both extra CSVs have SHA256
`d3a4aaff96db5c9a9d15cc9f4af8400f42b52fd4f97c08712dfce4d3d585562b`.
The qualified observer accounts for717760 samples:717731 raw-equal and29
invalid-only rows with both valid bits exactly0. The raw candidate pattern in
this run is1xx00101 versus00000101; original raw217 equality is NOT a PASS.
Both independently driven extra-epoch receipts prove two faults, three held
stalls, two one-sided resets and four recoveries. This is R0/D0/S0 only;
registered preflight and inverse-current/sticky-forward counters remain0.
Combined R1/D1/S1 preparation is now authorized offline, with no new source
or numerical-check changes and no actual/physical launch yet.

Healthy30-upper343 original69687 completed exit0, Vivado exit08:22:25UTC.
Parent reran the frozen context-specific result verifier successfully. Exactly
686 scores entered343 map words;687 were visible, with one checked provisional
tail. Forward input1536, forward/product/inverse-input/inverse1024 each,
prepare690 and ratio689 are actual stage exposure, not three completed jobs.
Native capture260, raw129/qualified121 tuples and52 packet reads match goldens;
publication19910/read-release20700 clocks, maxAXI8, remain inside old limits.
All12303 source/ingress samples are counted; canonical3618 and pilot512 exact.
Overlap witnesses: capture273, compute/coarse+pilot5393, compute-afterSTOP14259.
Map remains retained through native release8991, then releases at9000.
One actual late447 negative is authorized only after this outcome is archived.

The healthy343 preparation is committed at FWf9c595998e / HDL529dc8e8d3.
Parent checked all1663 portable hashes/1664 safe unique members, archive
`05bbf148e9651ceab0b3d3f0bf5eab31369c744e203727c9718bff7121c030df`.
Actual-result archives are being completed separately. The arithmetic actual
runner review identified subprocess-environment and failed-run integrity gaps;
only those runner safeguards and their offline tests are being repaired before
freezing an actual arithmetic launch. No runtime logic, numerical gates,
physical timing constraints, radio or PPU configuration changed here.

## Final30 rejection proof and source-specific timing-candidate launches

Late30-upper447 original4358 completed exit0. Parent reran the frozen result
verifier: expected-late-rejection PASS. Actual command handshake17179870177,
capture-start lead-50 and58 control clocks meet the predeclared negative bounds.
Native admission/capture/compute/raw/qualified/packet/result/IRQ all remain0
through the complete12303-sample source. Coarse894 scores,447 map words and512
pilot samples match their independent goldens. This is successful rejection,
not a native detection or RF result. All794 full-run hashes and536 portable
hashes independently verify. Portable archive SHA256:
`690ae23ad0fa0bc7a8b5e59d3b6923186067fe29e7c865295e2efab4df760353`.
Final30 FW5bf4019a4bd151ee2769703a81c3112d63da4fc0 is pushed on its isolated
DO NOT MERGE branch; HDL529dc8e8d33afc237c7b26f8969ec32fa97cdbdd was already pushed.
Healthy343 also has791 original-run and533 portable hashes independently
verified, archive5df8821406402188ef7d1eb5dd59d155583fc15247c43081e8d3f86841b2cbc4.
Passing control baseline22816 is archived at FWd802dbc3716ca79d7e3a10aec00e76d2ab1a97ff /
HDL04724da01d8917dbdb2abfbd54edf01e77d962fa; all69 archive hashes verify.

Parent read the complete settings-only control preparer, its new tests and
report. Independent94-test repetition passed in14.62s, original86375 exit0,
retained at `/tmp/starlink-combined-final-parent.qw8qxJ`. All298 archived hashes
and the complete live freeze verify; project was absent. One actual175
R1/D1/S1/extras1/QUICK0 run is now authorized from
`/tmp/starlink-completed-input.5EaJuD/extra-edge-combined-prepared-v1`, inventory
`8e9251fe06e41917e9e0b5ebceef36db444bc39770efe7acb940dbfcc4ed7906`.
Final FW6a8bce26b7ecc408a610efc139b60fb0d3c97414 /
HDL5c18664368eeaf1bf2f76a2a672dfbd3f78c167f. Frozen source bytes remain exactly
those of the passing phase-aware baseline; only settings/provenance differ.
Historical registered25ab9d06 CSV, both extra suites and independent status
accounting are mandatory. Baseline29 invalid-only rows are not a combined
expected count; no original raw217 PASS is inferred.

Parent finished arithmetic runner/test review, including sanitized Python
children, original-error retention, independent after-run source verification
and publication of results.json only after both statuses succeed. A deliberate
early-publication mutant retains the misleading JSON as negative evidence.
Independent180-test repetition passed in20.50s, original47153 exit0, retained at
`/tmp/starlink-arithmetic-final-parent.GFCzUe`. All3775 final-v2 archive members,
six new live sources and both42-file freezes independently verify; neither had
a project or launch receipt. Archive SHA256:
`d8ebb01d798fd8bcc4ce0cf15eda588a5f2f857210d0046a66a5ae84415b7ce8`.
FW4e7103d67d8372628d0162b0e196050ab20ea4d6 /
HDL5e4c2ad291ac682308ea65b2a48758b2d445b75c are authorized for the175-only pair:
R1/B0/O0 baseline manifestc0366928757d83ec61e8e772e01e498a5aa8c680ce8ef8e375d59d8c72ad445b;
R1/B1/O1 candidate manifestdf31efc303aee3bf3fb2b065839b672d70e9d8d7f454ff7e3602a77b0f10ad52.
Use only the final v2 freezes, runner33ba72515e0198fae920ef0b0e477a6c07b6c95f3552f3d5671078c2bef90ae9,
unchanged original bounds/assertions and event-indexed independent numerical
comparison. Output-derived scores are oracle-only, not scorer RTL integration.
Each agent owns its original handles; observation timeout never permits restart.
Failure is retained without retuning. No physical launch or promotion follows
automatically from these simulation authorizations.

The authorized runs have now launched once: control original79656 at08:40:10UTC;
arithmetic baseline44608 and candidate34776 concurrently. Their agents own
polling and original terminal receipts. No terminal result is claimed here.

The60 numerical work now has separate FW/HDL worktrees at
`/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired`, branch
`codex/starlink-rx-only-do-not-merge-high-rate60-paired`, based on final30
FW5bf4019a/HDL529dc8e8. Parent reviewed the pre-evaluation recipebd39c5fd:
approved198 support files are byte-exact, PCG64 seed0x600052020260910 is fixed,
16423 raw samples, separate x2 rounding twice, native264-tap exact replacement,
520-sample capture,257 raw/241 qualified lags, seven447-score coarse blocks and
512 independent pilot samples. Identity probes at offsets0/42/127/14023/16422
are fixed outside native capture before evaluation. No new runtime profile,
native60 service budget, actual FFT, RF accuracy or causal acquisition is claimed.
Primary runtime, radios and PPU remain unchanged; full-bank setup still fails
at-1.907ns. Hardware qualification and .18-before-.17 deployment remain open.

## Actual arithmetic pair: numerical prefix verified, full runs FAIL

Both original arithmetic handles terminate exit1: baseline44608 and candidate34776,
Vivado exits08:42:39/08:42:40UTC. Parent read both original simulate.log failures:
epoch14 PAYLOAD_PRODUCT_OUTPUT_MISMATCH, baseline old-shadow line72 at1261662920227fs,
candidate elastic-shadow line124 at1261765777375fs. This epoch deliberately forces
the bank product-overflow net; it follows the nominal/stalled and earlier fault
epochs. The wrapper's wire output versus the old core's register output may alter
what a hierarchical force exposes to the comparison monitor. That is a hypothesis
requiring independent diagnosis, not an established testbench defect or a pass.
Original assertions, source freezes and failures remain intact; no retry is
authorized. The agent is archiving both runs and may perform read-only saved-waveform
analysis plus a separate offline force-propagation reproduction.

Parent independently ran each frozen helper's verify_events on its recorded event
CSV. Both complete nominal/stall event sets pass19456 ordered words per transform
stream and16986 output-derived oracle-only scores. Baseline event SHA256:
`e475315242f059b6c38166bc858e21b1b302f17b8b36f9513b3a53263e452b97`;
candidate event SHA256:
`7bbe79fd2648984f0901296d69c1e168cac400426eb2642e91e24ff3815803f3`.
This prefix evidence does not satisfy the incomplete fault suite, original full
baseline CSV gate or full-run terminal contract. Both results.json files are absent;
the runner reports original failure with after-integrity success. No routed
timing, bank throughput, scorer RTL or deployment qualification follows.

Both failed runs are now preserved in the full-project/WDB archive
`22cdaa34c00226790ed1759a459eab4a28425111d53e169bfab93c73fb514b8e`.
Parent independently verified its93,784,281-byte archive and all336 safe unique
member hashes. No failed source, log, original terminal or waveform was replaced.

## Upper60 common-source numerical cohort independently repeated

Parent read the full465-line numerical helper, final tests/CLI and unchanged
pre-evaluation recipe. The separate x2 FIR stages use independent convolution
and per-stage rounding, checked against streaming x4 conditioning. Native257
integer tuples independently match the fixed correlation contract; coefficient
packing is checked separately from sample packing. Explicit18-bit C-model calls
reproduce the existing conditioned60 kernel and all seven blocks' forward,
product/inverse words and BFP exponents without changing global model width.
Wrong30 kernel/energy, wrong native66/132 geometry, component swaps, missing
halos, flattened single-round cascade and corrupted receipts/goldens are tested.
All26 native packet words and every coarse input/index/energy/map word are checked.

Independent final256-test repetition passed in16.94s, original55259 exit0,
retained at `/tmp/starlink-highrate60-cohort-parent.sQf2cv`. Parent then executed
the immutable v2 source_snapshot CLI's full rederivation: all69 numerical files
PASS. The v2 cohort is at the high-rate60-paired worktree's
`build/high-rate60-offline-v2/cohort`, source signature
`c56f812b79f5bb8d5b60bc70af43ad0b5f1579e5af0e74dd8516fabeb2237c0a`, cohort hash
`6de2f3645459f8649d8fee127e479991fb1cc55b75001a37c763223e716b4dfa`.
All69 numeric files remain identical to v1; added tests change source closure,
not recipe or numerical acceptance. Numerical stages16423→8205→4096 have zero
clips; coarse3129 scores use conditioned60 Eh1073765335. Native264-tap Eh1073758594,
520 capture samples,257 raw/241 qualified tuples, known winner0 and power
1152957518188856836 are exact deterministic-fixture results. Pilot512 selected
outputs have raw support[34359735227,34359749686), step24; full683 offline outputs
and90 initial unsupported outputs do not predict hardware auto-stop counts.

Archival/pins remain in progress. The next stage is offline preparation of a
native60 service probe with a genuinely60MHz sample clock and declared admission,
capture, compute and release bounds BEFORE measuring service. The old generic
native bench's #7 clock is not a60MHz source. No actual60 simulation, continuation
tail, public profile admission or routing is authorized by the numerical result.

Final60 FWf62b0716ccf660c7aac600be00d0f063b34a3a89 and unchanged
HDL529dc8e8d33afc237c7b26f8969ec32fa97cdbdd are pushed to the new isolated
`codex/starlink-rx-only-do-not-merge-high-rate60-paired` remotes. Parent verified
all310 artifact hashes/311 safe unique archive members, SHA256
`41cf3d35fb4f9b6a182490f3db71036594ddd021141466ece2e9b045c6f53f66`.
The final report corrects one archived table row: the26-word native packet
contains request and coefficient-generation IDs; visit60000052 is separate
fixture context, not a packet field. No numerical source/recipe/archive changed.

## Combined control actual175 PASS, physical preparation next

Original79656 completed exit0; Vivado exit08:50:04UTC, wall593.59s. Both complete
589950-line main CSVs equal the unchanged registered historical SHA25ab9d06...;
both33180-line extra CSVs equal
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
Parent verified both pairs and the complete input inventory, executed only the
frozen Tcl receipt procedure offline, and independently ran the frozen observer
audit:1246258 samples =953795 raw-equal +292463 invalid-only. Every invalid-only
row requires both status-valid bits exactly0 and all other216 fields equal;
all rows remain retained. This is qualified-protocol equality, not raw217 PASS
or a determination of the invalid payload's driver origin. The earlier29-row
baseline observation was not used as a combined expected count.

Combined settings are exactly R1/D1/S1/extras1/175/QUICK0. Both independent extra
suites prove2 final faults,3 held stalls,2 one-sided resets and4 recoveries.
Original44 healthy blocks,84 registered preflight cases,12 active input-fault
cases and literal current/sticky reason/retirement checks complete. Actual
comparison has780367 active checks,36 identity consumptions,270 permitted private
differences,2 final-fault edges,99936 owned stalls and143 reset-owned edges.
Inverse-current/sticky-forward counters remain0; no coverage is invented there.
Root's first supplemental audit command used a wrong extra-CSV basename and
exited1 after successful status/main validation; the corrected read-only filename
check passes. That was not an actual simulation failure or restart.

Lossless archival is in progress. After archival, the next authorized work is
OFFLINE physical preparation and tests only. The old synthesis script cannot
be called directly: it reads old scope.txt and forwards only R, omitting D/S.
A reviewed adapter must admit only this fully verified111 actual result, freeze
the exact seven runtime bodies and IP/kernel/XDC/directives, explicitly bind
all three options and reject missing/wrong/failed evidence before launching.
Keep unchanged100/175 diagnostic constraints and full pre/post source checks.
No synthesis, placement, route, arithmetic graft, primary runtime promotion or
radio action is yet authorized by this checkpoint.

## Next-stage native60 contract and arithmetic force diagnosis

Native60 service-probe recipe is committed before any measurement at
FWd6408a2e59623c7ba9f0bd07e83bce23401e003f, HDL unchanged529dc8e8.
Parent inspected the actual capture bridge, sliding correlator and DSP reducer
state machines. The declared healthy single-job/free-store100MHz bound includes
3*520+64 capture transfer,520+16 sample energy,257*(264+16+16) sweep/reducer and128
publication cycles:78360 total, below84000. Readout uses at most140 dedicated
AXI transactions of24 cycles each,32 retention and24 release-settle cycles;
84000+3360+56=87416 is below88000. These are conditional bounds, not measured
service or host/network timing. The source has exactly16423 samples/no added
tail; the sample clock continues after valid stops. Completion must include
all257 raw handshakes and engine/bridge idle, not just the result following
qualified lag120. Observe256 further no-stale control cycles after source-off,
public release and full drain. Implementation/compile-only policy tests are
authorized; a native RTL service run still needs source-specific review.

Parent independently verified the original72-file combined-control archive
inventorye908dac935b0bebe362ff516bf7f4e04ce31b5cad4b321e5fabc0b2f83e75cb3.
Its monolithic compressed waveform is105807603 bytes. Before remote publication,
lossless<=40MiB parts with whole-compressed/original-WDB hashes and safe
reconstruction tests are being prepared. Original local waveform/project and
unpublished commits remain preserved; no oversized blob was pushed. Only the
agent's two own unpublished archive/report tips may be amended after local
backup refs; there is no remote history rewrite or source/measurement change.

The first minimal Icarus force test contradicted the initial alias hypothesis:
both direct and wrapped registers changed there. That failure remains retained.
Read-only Xsim WDB queries preserved before/after hashes, but the original WDB
only recorded top-level signals; listed internal paths have blank histories.
It cannot establish the actual bank failure's exact119-bit compared vector.

A separately authorized standalone Xsim diagnosis now completes in both modes,
original4397/90953 exit0, without FFT/IP/bank execution. Parent read its full
bench/runner, verified all five frozen source hashes, both phase/terminal
receipts and all six force observations. Frozen bench655ab728..., runner3f0374e0...,
directory `bank-arithmetic/hdl/library/starlink_pss_acquisition/build/bank-arithmetic-force-xsim-v1.x51G4v`.
For overflow/position/start, Xsim leaves original direct-core output registers
and wrapped inner arithmetic registers unchanged while the wrapped output wire
monitor sees the injected value; release restores it. Overflow changes only
bit1 (XOR2); ordinal64→19 changes XOR0x53<<72; start changes
(0x2000e0000 XOR0xdeadbeef)<<2. This reproduces a simulator-specific monitor
boundary distinction, not an actual-bank internal waveform or arithmetic PASS.

Only offline preparation of a three-field observation-binding adaptation is
authorized: preserve the full119-bit predicate, all original force/veto/fault
stimuli and runtime source bytes; observe the same register boundary for those
three fields without masking fault epochs or dropping comparisons. Genuine
arithmetic-corruption mutations and wrapper-transport consistency must remain
detectable. No actual bank retry or arithmetic physical trial is authorized yet.

## Portable control evidence and narrow monitor-test review

Control evidence packaging is now independently qualified. Parent read the full
lossless reconstruction helper, ten tests and archive README; repeated10 tests
PASS in0.52s at `/tmp/starlink-wdb-parts-parent.B2lsyM`, including the actual
105807603-byte gzip and116445321-byte WDB reconstruction. Original hashes remain
bbc9ffd1d907b80ed4522b0b2d28b1ee62ead1810fc542681a12908b6e8341ea and
12d13666cf7d62c65581d66150539e2105c5db06d0c621357affb54da3f8a20f.
All83 portable inventory entries verify, manifest
`62cfb6821f8a2a4e98664103cffd083b2e92f6690da9293d287b009a671e6914`.
Parent also checked both original unpublished backup refs, exclusion of those
oversized commits from pushable ancestry and every newly reachable blob<=40MiB.
FW45c2f8a325e4911d31f117098e17f591e7149c9e /
HDL903f9b6823506847b078ee36b893a095ce756b78 are pushed to the existing control
DO NOT MERGE remotes. The only removal was the monolithic gzip's tracked entry;
the complete local file and original WDB/project remain intact, and remote parts
reconstruct both exactly. There was no physical or simulation change.

Arithmetic failure diagnosis is committed and pushed at
FW2547051646fd759b9b513b8d7f1e57e3673447c3, HDL unchanged5e4c2ad2.
Parent independently verified all120 diagnosis archive members, SHA256
`cddc86d78eb0e2275af50006391ecca3cf1ecb239bc699bd3e1abd182b72a3a9`.
The original336-file failed-run archive remains unchanged and is also remote.

Parent reviewed the draft monitor-boundary tests and exact six-reference delta
(three fields in each of two observers). No field/checker/epoch is removed;
the entire old bench inverse remains checked. Frozen wrapper/core hashes prevent
a changed transport assignment from being hidden by the register observation.
Offline tests cover healthy option combinations, genuine overflow/position/start/
I/Q arithmetic corruption, missing/extra rebinding and real guard/mailbox veto
with an explicitly synthetic non-FFT interface. Offline execution is authorized;
no actual-bank retry is authorized. Additional bounded internal-wave logging is
being prepared so a future failure does not again lack its compared vectors.

Parent also read the initial native60 bench/check include. Before measurement,
the final preparation must explicitly check per-tuple reducer hold<=16 and held
tuple stability, plus known valid/ready/command/capture flags after configuration;
the total deadline alone cannot prove these per-step conditions. The clock origin
is unambiguous: starts0,2.1ns offset then first half-period; first positive edge
10433333fs, first negative edge18766666fs. Source/numerical/deadline contracts
remain frozen, and the first native service measurement is still not launched.

## Independent monitor gate and source-specific actual launches

Parent read the complete final monitor helper,265-line policy, six-reference
bench delta and40-line diagnostic Tcl. The runner's sole change selects that
diagnostic Tcl; runtime arithmetic, full comparison predicates, original fault
stimuli and numerical vectors remain unchanged. Parent repeated226 tests PASS
in22.92s at `/tmp/starlink-arithmetic-monitor-parent.K4YnWa` (original77195,
terminal0), with Ruff PASS. Parent independently verified all8295 archive
members, all five live sources and both44-file prepared inventories (original
45309,terminal0). Archive SHA256:
`9b7ff3bf21f94aaaf59f31e21fc0b0f0ae326628e23049b51b874866cf202acc`.

FW`deb023b36b2780bd25aa5257eee52d905a662174` and
HDL`18aa1b6f58fe7abcf06672fccf6d93551174de54` are pushed to the existing
bank-arithmetic DO NOT MERGE remotes (original35207/32134,terminal0).
Root authorized exactly one actual vendor-FFT run per175MHz v3 preparation:

- R1/B0/O0 baseline inventory
  `440e349ac6c245cec032e18b717dc52037ed7e0b53f777d984aee9c0e2b43b2f`;
- R1/B1/O1 candidate inventory
  `6376f1fb2508f357933d4cb9cd9949d8da452d155a47084701aa29fb99df1954`.

The agent rechecked both inventories and runner684f8e78 before starting the
original handles65522/58122 at09:22:56–58UTC. It owns their polling; no restart
on observation timeout is authorized. Results remain pending. Original failed
actual runs are not relabeled. Full historical baseline CSV, event-indexed
candidate/fault checks, source/IP post-integrity and recorded internal waveform
histories are required. No synthesis, route or radio action follows implicitly.

Parent also read the complete native60 bench/checks, helper and preparation
tests. Review found Python numeric-type aliases in recipe equality and
case-sensitive fatal parsing; the agent corrected both and added negative
tests before freezing or measuring service. The actual native compile remains
compile-only. Its517-test combined preparation/numerical result is agent-reported
and awaits an independent parent repeat and final bundle review.

The control physical adapter's complete initial source/tests were reviewed.
Its fixed constraints/directives and explicit R/D/S binding are retained.
Before physical execution, independent Python children must clear vendor and
Python path overrides without changing Vivado's parent environment; offline
poisoned-environment coverage and a post-failure integrity audit are being
prepared. No control physical launch or full-receiver promotion is authorized.

## Native60 first service attempt: pre-command readback failure

Parent independently repeated517 preparation/numerical tests PASS in21.96s at
`/tmp/starlink-native60-preparation-parent.QNdffV` (original6536,terminal0).
The generated parent-test bundle is byte-identical to the final prelaunch
bundle, SHA256
`45e61eec6c2f40916af9f767631ca8281cef338bab06674732bcc5ee6af7ca1a`.
Parent verified its158 file receipts,87 live/snapshot source hashes, unchanged69
numerical files and compile-only pre/post integrity. Source signature is
`d85c9db9e6f7d84217dc17b0d923f5ddcd9a37b5ecd1d3033a8f50a3244bd897`.
FW`6fb7944aff1230652ba952c824f22902a5b0aa7e` and
HDL`50880a4a57c8105c91097651a2dae8ea3ff8d366` are pushed to the60 DO NOT MERGE
remotes (original98845/56202,terminal0). No runtime HDL changed.

Root authorized one native-only service run of that exact frozen bundle in
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-v1`. It terminated EXIT1
in0.1725s (original agent tool chunke3a218; no live session was issued), before
submitting a command. Configuration readback passed. At control cycle8295,
source count3357, the bench reports
`native60 public current-index snapshot outside admission window`.
No native service result or timing bound is established.

Parent inspected the original log/status and independently verified the frozen
bundle, identical before/after source and69-fixture inventories, compile exit0,
simulation exit1, no integrity error and no success terminal. All3357 logged
source beats equal the original prefix. Capture, raw-tuple and hold logs are
empty. Original failed inputs and output remain intact; no retry is authorized.

The public current index is sampled through a source Gray register and two
control-domain registers; reading the low word captures the high-word snapshot.
The bench currently applies the actual command-handshake window to this earlier
public readback as well. That is a possible test-model error, not yet a measured
diagnosis: the failure message does not include the returned index. A minimal
print-only diagnostic is under review. Any correction must preserve the real
handshake window, original source, full native search and all declared deadlines.

## Arithmetic v3 complete benches; automation log-source failure

Both original actual handles65522/58122 have terminated EXIT1; agent reports
vendor exit09:27:00 baseline and09:26:54 candidate. Both benches reached all11
functional terminal markers, including the complete original fault/reset suites
and `BANK_ARITHMETIC_ACTUAL_PASS`. The collector then failed because the custom
Tcl diagnostic marker is in the outer Vivado log, not the HDL `simulate.log`
that it reads. Both `run_status=1`, `after_status=0` and absent `results.json`
remain unchanged. This is not a successful automation run.

Parent independently ran the unchanged helper's terminal/event checks and
verified all11 markers,76 nominal/stalled core-job records with the original
service contract,19456 exact ordered words/stream and16986 output-derived
oracle-only scores per mode. Baseline full historical CSV remains
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
Candidate accept-to-bank latency is4 clocks versus baseline3, as predeclared.
All44 frozen inputs and generated FFT wrapper before/after/live hashes verify.
No scorer RTL or physical timing claim follows from these oracle scores.

The same unchanged diagnostic receipt predicate passes on original outer logs
with111 baseline/115 candidate signal paths. Parent-verified outer log SHA256:
baseline `1be6604273852b95b0f900cc7e10470612dcd517ab8e43ac72b38c3e2b70268d`;
candidate `3a8037b2e7b9fbcfb1f3b86b2884d76a10db33e57634e7eff957c5fd482dc033`.
Actual internal waveform histories remain under read-only verification. A
minimal log-provenance correction and separately labeled post-hoc assessment
are being prepared; original automation records will not be overwritten, and
an identical simulation rerun is not authorized merely to relocate a marker.

The native60 v1 failure archive also independently matches all241 original
files:1709940 bytes, SHA256
`200ec173c89f24dea9ca50d3633d8e1c7e74a3b5060d701702660794cc9bfaa0`.
The public interface README explicitly documents readback synchronization lag.
A new-copy print-only diagnostic may be prepared, but execution awaits exact
source-delta review; the original failed bundle and search gates are unchanged.

## Actual internal histories and native readback diagnosis

Parent read the complete read-only WDB query script and independently checked
all333 baseline/345 candidate values against the exact111/115-path inventories
at three fixed times. All queried internal histories are recorded, not blank;
before/after query hashes match the original live WDB/inventory files. At the
former epoch14 failure time all four119-bit monitor vectors in each run equal
`600ba0066440280000000800380000`. Both references and inner arithmetic overflow
are0 while wrapper/raw overflow are1, directly observing the intended
register-versus-forced-wire boundary in the actual bank. Query processes
79313/1613 terminated0 without advancing simulation. A dedicated exclusive
diagnostic receipt file is approved for offline collector preparation only;
the current assessment uses hashed original outer logs and preserves EXIT1.

The independently verified native print-only diagnostic bundle is
`16fc0b020b9a42f74863aa1f5af8871f7f47777233cf20168f7762679a606438`.
Parent verified exact inverse of two displays/read-line split, all86 other
sources,69 numbers,87 live originals and unchanged budget before authorizing
one diagnostic execution. Original tool chunk10ed81 terminated1 in0.2249s,
without a live session, in
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-diag-v1`.

Observed low-read completion: cycle8288, public high half intentionally not
read yet, low word000000bf, hardware captured snapshot00000008000000bf.
High-read completion: cycle8295, coherent public00000008000000bf, live index
00000008000000c7, synchronized00000008000000c6; trigger cycle8282. The returned
index34359738559 is exactly trigger minus one. The original assertion still
fails at cycle8295/source3357, with zero capture or raw tuples. Parent verified
full source/fixture before-after integrity and exact equality of all source,
capture,raw and hold logs to the original failure. No service PASS is claimed.

Offline test-only correction is authorized: witness the actual low-register
capture and require exact completed64-bit public coherence, separately bound
CDC/readback age, and keep the actual command/lead/source/service bounds literal.
At low-register capture the ideal-clock offered-index lag is at most
ceil((2*10000000+8333333)/16666666)=2 samples. At completed readback, two
<=24-cycle transactions permit at most48 control cycles and an additional
ceil(480000000/16666666)=29 samples. These are separately derived readback bounds,
not a relaxed command deadline. Missing/duplicate/future/stale/incoherent
readback cases must fail. Corrected service execution is not yet authorized.

## Exact111 synthesis and diagnostic route

Parent fully reviewed final physical-preparation/owner code and independently
repeated43 tests PASS81.93s, original29431 terminal0,
`/tmp/starlink-control-physical-parent.6YHg0T`. Final preparation inventory
`99862b8d88414de6b2b4171df2a1a61bf5849ef2effed3c875de9904c366f158`
and all129 offline archive hashes verify (archive inventory
`a980304b1489876bd98f93ecea30fd5aca0f16e382c8523e28f8b0412a9d092c`).
Tested sources FWb0b43802603c18472c65c159a36424785441af1a /
HDL26cc65a7f473ba3f528c90524df35ff0b25b7466 remain unchanged in the archive pins.

One authorized synthesis original41784 terminated0 in108.90s,
09:43:14–09:45:03UTC. Parent checked all8 product hashes, all13 scope-declared
source/generated-IP hashes, the copied closure, explicitR/D/S111, actual100/175
clocks, zero-black-box receipt and process/before/after-integrity0.
Synthesis:1970LUT,4478FF,21DSP,15RAMB18(7.5tiles).
DCP `exact-control-combined-synth-v1/synthesis/fft_bank_owned_synth.dcp` under
`/tmp/starlink-completed-input.5EaJuD`, SHA256
`00cd669cee367f2ff9b3852d7fd05827ba64027ccd526f1f269cde5ddff630d9`.
All43 synthesis archive entries independently verify, inventory
`d35dd92a792d5555aafb0274e3da8eb501c50be4294e676350471338180d0fb6`.
FW55d7fbba5b8f32798f99ae568c51cb0be2c837c5 /
HDLfbb6ba6de76e4750ea6f04e87cbf1edb4078c96a are pushed to the control DO NOT MERGE
remotes; no runtime promotion occurred.

New unqualified finding: CDC-10 critical1 from distributed cause sticky Qs
through the combinational fast_fault OR to fast_fault_slow[0]. There are139CDC-15,
5CDC-3 and114/124 missing input/output delays. These are not waived.
Root authorized exactly one diagnostic route on that same DCP using unchanged
route Tcl0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a,
same100/175 constraints/directives, new
`/tmp/starlink-completed-input.5EaJuD/exact-control-combined-route-v1`.
Original98808 terminated0 at09:51:23UTC after46.956s, with all6630 routable nets
routed and no routing errors. This is tool completion, not timing success:
island175 setup -1.761ns/TNS -517.240/523 failing endpoints; global setup
-1.862ns/TNS -615.411/668 failures; hold +0.071ns with zero failures.
Source100 setup +2.217ns, crossings100-to175 -0.711ns and175-to100 -1.862ns,
async recovery -0.038ns remain explicitly reported. Routed area1975LUT,
4552FF,1077slices,58 control sets,21DSP,15RAMB18. Worst island path is full
product metadata validation through result acceptance to kernel-ROM enable:
6.948ns total,1.572ns logic plus5.376ns route,9 levels. The improvement from
prior -1.907ns is0.146ns, not closure or the best historical result.
Parent read the full route report, route-status and original exit/post-integrity
receipts and independently verified all37 archived files. Archive inventory
`a870afb08a029cc48b0f13828a7577d048de844bf6aeccab4a9624461a8c430b`;
routed DCP `c45ac64b6731d8709cbab9fe57fdcd96c517e9d0f265017d958d2ca110537349`.
Immutable archive pins FWbdd2fd5e3e6da0da1831dca8db5793cbf9a1ddba /
HDL2ccfac2e70da2689d97eee75cbfc78e2589813a2. No exceptions or source edits
were applied to this failed checkpoint. This is not a physical-release pass.

Read-only CDC diagnosis favors two-stage per-cause synchronization with OR only
in the destination domain: worst-case+22 sync FF, no nominal extra sampling
stage, unchanged immediate fast-domain fences. A simple registered export of
existing fast_fault would instead add one fast-clock cycle and is not exact
retirement timing. Offline per-cause candidate/tests are authorized; no new
actual FFT/synthesis/route is authorized by that preparation. Common epoch and
private-core-reset separation must remain unchanged.

## Native60 complete standalone service PASS

Parent reviewed the exact readback-only correction and independently repeated
575 tests PASS19.95s, original34984 terminal0, at
`/tmp/starlink-native60-readback-parent.LuaPUs`. Its generated bundle is identical
to final91-source/162-receipt bundle
`bbcb423cf7d1f73bd6a6e7be3666aafe1eaa80414f7d99384ec5ad73c049ba83`;
all live/snapshot identities, original69 numerical/76 source bytes and original
service recipe verify. Corrected source pins FW0c49f441030c9507d1e1f7391a3b563cd13b5bb7 /
HDL706ffb7b5b842409d8a8714c056203d8b5555034.

The single authorized native-only run original75987 terminated0 in
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-readback-v1`.
Parent independently reran the frozen result verifier, checked original
compile/simulation0, no error/integrity error, identical before/after source and
working fixtures, and all source/capture/raw/hold inventories. Measurements:

- Actual command index34359738591, lead1664,52 control cycles after trigger;
  original command window/lead/deadline all pass.
- All16423 source samples,520 captured originals,257 raw/241 qualified tuples,
  exact powers/saturations and two26-word public packet reads pass.
- Capture-end11974; publication84472 (72498elapsed), release85261 (73287),
  full257 drain/idle86616 (74642). At simulated100MHz these are724.98/732.87/
  746.42us. Original84000/88000 limits unchanged.
- Publication is at raw249; release at252; final5 raw tuples complete later.
  No early packet/release is substituted for full completion.
- Per-tuple hold max11, AXI max7,105 readout transactions; source-off30072,
  56544 configured compute cycles afterward; final256 no-stale cycles and154
  continuing source-clock edges. Health0, no IRQ/result/work left.
- Public snapshot low capture8284/read return8295 equals34359738559, capture/return
  lags1/8 within separately derived2/31 and read-return11 within48 cycles.

Parent read the complete outcome report and verified all246 original archive
files,1814229 bytes, SHA256
`59a36a1b36bb05c9f0be992596080ecb998d12e391e2d03cdafa6d7944d7e3aa`.
FW3c949b445b0208d6b1f5f72571fc5da1eeb0f2eb and HDL706ffb7b are pushed to60
DO NOT MERGE remotes. Both earlier pre-command failures remain separate.
This proves one healthy static-known-center native60 job, NOT native RF accuracy,
queued capacity, paired60 PSMA/PIL1/FFT or deployment. The next paired60 step is
read-only proposal preparation from the same raw cohort and existing30 harness;
runtime admission changes and actual paired execution still need review.

## Portable arithmetic assessment and future receipt fix

Parent reviewed the full post-hoc script/report and future exclusive receipt-file
fix, then independently repeated246 tests PASS24.60s, original91085 terminal0,
`/tmp/starlink-arithmetic-receipt-parent.dr2uuN`. This includes full six-part
archive reconstruction and all341 original member hashes. Parent also independently
verified all9644 additive post-hoc/offline/future-source archive hashes, SHA256
`bac2e967d91fa4e5a348084c049bbb6387e24bd3f40a55ebeaa48329f8683468`.
Original241304017-byte archive470f5a8c remains intact locally, exactly ignored;
only lossless<=40MiB parts are pushed. No new reachable blob exceeds100MiB.
FW19dcc9c867c3cde285a2d9ca6c7d2a08c022f077 /
HDL8bbfee6ebb1d77b58b33080e8a58bdcca978fd28 are reviewed and pushed to their
DO NOT MERGE remotes (parent17915/74833 terminal0). Original actual automation
failures remain failures, while the
separate complete functional/source/WDB assessment passes. Offline source-specific
OOC preparation for R1/B1/O1 is authorized, not physical execution or a new simulation.

## Next isolated 60 paired admission gate

Parent read the current public wrapper/controller admission, energy/identity and
two-stage DDC counters against the agent's read-only integration proposal.
Offline StageA60 implementation/tests are authorized in the isolated60 worktree:
default-off ENABLE_BANK60_PAIRED, strict source60/bank/shared/realtime/pilot/STOP
and conditioned Eh1073765335, distinct PSMA1.8 identity, unchanged legacy30/default
profiles through a strict source inverse. In new mode only, a saturating sum of
both DDC discontinuity counters exposes first-stage failures even if shutdown
prevents downstream propagation; document stage events, not unique raw gaps.
Test reset-only lifetime, flush/disable retention, retained-map terminal health,
unknown/invalid options and exact public identities. This is not primary runtime
promotion, host/kernel ABI admission, paired actual FFT authorization or hardware.

The later common-source harness may account for two disabled-DDC CDC-prime beats
separately from the immutable16423-sample cohort:16425 offered beats, no tail.
It must retain native full257 drainage after source-off, independent pilot512,
894 map admissions/447 words, actual coarse/native overlap and all visible
numerical boundaries. Existing30 startup/release assumptions must not be copied
blindly: source60 ends before native completion. Causal acquisition, shared-bus
capacity, full receiver timing and 300s RF comparison remain separate gates.

## Arithmetic OOC preparation independently qualified

Parent read all three new Python helpers,662-line test file, the complete adapted
synthesis Tcl and report. Independent316 tests PASS48.37s, original35834terminal0,
`/tmp/starlink-arithmetic-ooc-parent.T00php`. This is70 new preparation tests plus
246 existing monitor/policy/arithmetic/retirement/payload/archive tests, including
the original six-part archive reconstruction. All7469 safe regular members of
the preparation archive independently verify,22493729bytes, SHA256
`34de20f4867838aebab0e8f3748c0462e0467434831687347b8282d906916bee`.

Frozen preparation inventory
`c249a13a4e34aa393513fa955199407eef0a569484025d1e5cdb5fc83cb185ce`
contains23 inputs/receipts and independently passes its frozen verifier against
the unchanged original v3 evidence. Source-specific admission preserves the exact
original automation FAIL while reverifying11 functional terminals,76 core jobs,
19456 ordered words per stream and345 recorded WDB values. No generic failed-run
admission, replacement result, altered source or future receipt substitution.
The adapter strictly restores f843af03, binds and reads back R1/B1/O1, preserves
100/175 clocks/IP/directives/two threads and independently audits copied inputs.

FWa17b6656f8e48be562063d0adcc8c2d791128a1f /
HDL5b68bb8b488a886c3861537eaf9643ec940003e0 are reviewed and pushed to the
arithmetic DO NOT MERGE remotes (root66302/45851terminal0). Exactly one synthesis
is authorized from the frozen owner, new
`hdl/library/starlink_pss_acquisition/build/arithmetic-ooc-R1B1O1-175-owned-v1`
in that worktree. Original59427 terminated0 after98.743s at10:09:40UTC, with
before/after audits0 and a unique synthesis completion marker. Parent independently
verified all8 product hashes,15 scope hashes (14 synthesis inputs including the
generated VHDL plus original simulation log), explicitR/B/O111, frozen copied-source
closure and actual clock/resource/CDC reports. Synthesis1944LUT,4547FF,21DSP,
15RAMB18(7.5tiles),zero black boxes. Product wrapper/core55LUT357FF4DSP; no
whole-receiver fit or arithmetic mapped-register claim follows from this count.
Source100 period10ns/island175 period5.714000225ns; CDC139warnings6info,
114/124 missing I/O delays,zero unconstrained internal endpoints. These remain
unqualified. DCP2128454bytes, SHA256
`de5b7ca6849c8111ccfce29ca39bbf8899276c0dea309abb576e70546daf06bf`.
Parent subsequently authorized one diagnostic route on that exact DCP with the
unchanged0873675f route script, clocks/directives/two threads, unique owner/output
directories and independent before/after DCP/script receipts. Original42281
terminated0 after58.32s; owner `/tmp/starlink-arithmetic-route-v1.VNX5gK`, output
`route/`. Parent read original process-time exit0/unique completion marker,
route status and all timing-summary groups, verified original before/after
input DCP/script hashes and routed DCP
`e8a6336eb4079d8d27ac9596cd6fcb7322da656d0f8f04d6ac67e619ed5a7413`.
All6762 routable nets complete,zero routing errors. Still timingFAIL:
global -1.341ns/TNS -386.804/497 failing; island175 -1.341ns/TNS -304.384/379;
source100 +2.454ns;100-to175 -0.629ns/40fail;175-to100 -1.222ns/78fail.
Global hold +0.038ns withzero failures; async recovery/removal +0.292/+0.621ns,
zero failures. Routed1994LUT4557FF1082slices21DSP15RAMB18; CDC/IO still open.
Worst internal expected_position[1] to descriptor CE:6.766ns=1.863logic+4.903route,
six levels. It remains a current-input validation/control path. This is separate
from the exact111 control/CDC branch, not a combined candidate or fullreceiver.
Read-only next-path/combination diagnosis is authorized, no new RTL/physical run.
Synthesis archive134regularmembers independently verified,24033138bytes, SHA
`5ea5d69dade968670665c8773eec48cc55fe55a7ac95490e50f2de695c41dd07`;
FWe7142938e097cfeb22c7ce38f409023e3fc66739 pushed (root72369terminal0).
Parent subsequently read the complete route report and verified28 safe regular
archive members,5472969bytes, SHA256
`dac5af7b24c94615fc3cffd2e4c83ae0ccfd632b0a51b8d3fda76194a7d6c5c0`.
Route package FW2d050cea9e5769681911c7c3e1d86420c65f837f retains unchanged HDL.
After reading the complete input guard, parent authorized an OFFLINE default-off
local first-admission CE candidate: capture only job_started/descriptor with
!protocol_fault&&job_start&&!job_started inside the existing reset branch.
slot_open already requires job_started, so pre-admission framing/delivery faults
are closed; duplicate starts still prevent any second capture. This is a proposed
exact predicate factorization, not a delayed fault check or speculative descriptor.
All other fault/certificate/cursor/complete equations must remain literal, with
full old-field/transition/X-Z/reset/mutation proof before any actual or physical
execution. D/S/CDC branches are not combined by this authorization.

## Per-cause CDC offline recurrence reviewed

Parent read the default-off wrapper delta,110-line bench, strict inverse and
mutation tests. Independently122 tests PASS22.60s, original67758terminal0,
`/tmp/starlink-fault-cdc-parent.SqQ3mm`:37 new CDC/compatibility checks plus unchanged
49 exact-control,17 forward-retirement and19 payload checks. Full old seven-module
bodies and actual bench restore exactly; the only old test-helper change is a
four-line composition before the untouched inverse. Six malformed CDC bodies
reject rather than being stripped. Original30PASS and48PASS/1structuralFAIL
attempts remain preserved before the compatibility correction.

The new branch synchronizes twelve sticky cause bits independently and ORs only
the destination stages; fast-domain current fault and publication fences are
unchanged. Nominal digital recurrence,4096 subsets,48 X/Z rows,three clock phases,
both scheduling modes and epoch/private reset separation pass. Quiescent FFT
stub/forced source-Q snapshots are explicit: not actual FFT, analog CDC or physical
closure. Tested sources FW640cf54b8a28e979e62f90a8c57e911bb789ac7c /
HDL02de07cc7a6c241dd6cc8cf5b733037d89eac6bd. Parent read the complete report and
verified306 local archive members, manifest
`ed977a4e8cb185869ff355a474bde01ff9dcf8b72e252f50834fadf286984891`.
Offline actual-preparation is authorized: keep frozen dec20R1D0S0 independent
reference, old predicates/stimulus and historical passing111 main/extraCSV
expectations literal; new candidate R1D1S1C1 adds a slow-clock scalar stage
observer and explicit knob binding. No vendor actual execution yet.

Parent found a publication defect before pushing the CDC package: global ignore
rules omitted logs/reports from Git despite local manifest checks. The previously
pushed synthesis/route/physical-offline archives had the same issue; original
actual83-member package was already complete. All original files remained local.
Agent additively committed312 exact manifest-listed ignored files, no runtime,
test, manifest or original result changes. Parent independently checked ALL598
member SHA256 values and five manifest hashes through Git objects at
HDLae7c0ec29812efb2c0d442cbe9dfb6b3b0eaab24; each tracked path set equals exactly
its manifest members plusSHA256SUMS (307/38/44/130/84files). Earlier local checks
are not retroactively described as remote completeness. Corrected
FWf3393233375c4af8a8be15f59723b63fe1412b42 / HDLae7c0ec2 are now pushed to
control DO NOT MERGE remotes (root79563/16467terminal0). Prior failed-route
source/DCP and CDC122-test identities are unchanged.

## StageA60 public interface independently tested

Parent reviewed both runtime changes (40 additions/4 deletions), the153-line real
cascade/counter-specimen bench, complete new test/helper/inverse/manifest files
and four-line legacy inverse composition. Independent660 tests PASS25.11s,
original90816terminal0, `/tmp/starlink-psma18-parent.EdANJN`. Exact sources
FW6e561ee50b299d32991f636932eeccc467159303 /
HDLf16dc564c541df614a7c2b27c489aece5320dc43; unchanged during the replay.
Coverage includes strict opt-in initial admission and X/Z guard mutations,
exact ABI/kernel/Eh/DDC identities, positional/default legacy profiles, both-stage
discontinuity sum, first-stage-only and propagated real cascade faults, saturating
sum boundary specimens, cumulative reset/flush/disable semantics and four complete
public PSMA/map lifecycle variants with a real x2 fault producer. No specimen
counter interface is described as real filtering; the wrapper test uses an
inactive acquisition core. Old30/boundary/health/shared plus numerical30/60 and
pilot/coefficient/support tests are included. No actual paired FFT/native/PIL1
composition, live profile switching, host/kernel1.8 admission or deployment is
proved. Portable archive/report publication and next combined-harness preparation
remain in progress; no actual vendor simulation is authorized for this source yet.
Tested runtime/source pins f16dc564/6e561ee5 are now pushed to the60 DO NOT MERGE
remotes (root51007/98657terminal0). Parent authorized OFFLINE additive combined60
harness/preparer/strict oracle work using the unchanged69 numerical artifacts,
original native command/service limits, explicit two disabled prime beats and no
added source tail. Full257 native drainage,512 pilot outputs,447x2 coarse STOP,
every visible FFT/score boundary and measured clock-level overlap are required.
Historical30 benches and native arithmetic stay untouched. This authorization
does not include actual FFT execution, host/kernel ABI1.8 or radio access.

## Repeatable committed-evidence gate

Parent added read-only `tools/verify_starlink_git_evidence.py` and30 tests to
prevent the discovered ignored-file publication defect recurring. It requires
an immutable commit ID, an externally pinned manifest digest, exact committed
regular-file closure and every committed blob's SHA256. Working-tree/index
files do not satisfy the gate; it does not claim network publication or test
validity. Initial30PASS0.20s and real five-archive598-member Git-object checks
pass; the same checker rejects the original incomplete route commit2ccfac2e.
An initial shebang/filemode lint failure was fixed without behavioral changes.
Usage and evidence scope are in
`reports/experiments/20260910-git-evidence-publication-check.md`.
Final checker30PASS0.23s at `/tmp/starlink-git-evidence-final.Q0wsRK`; lint/diff
checks pass. This is additive firmware verification tooling, not PPU or RTL.

## StageA60 portable package verified from Git

Parent read the complete final report and collector (collector is not executed
by the660-test suite). At FW82cb23a5e787727d8e8bc26e97cfa95a06a97d64, read both
tar and inventory directly from Git objects and independently verified every
one of5254 safe regular members, including exact embedded receipt contents.
Archive4675650bytes, SHA256
`4887cee88e664b0deb2b9dfde571aff0246a1d63574e689bf22eb0ddc47d2111`.
All109 before/after/snapshot/live source identities independently match signature
`27aff0c356977ea1597256488c76b8dbcdb6cb36e9d22d66b5e8f494399b983f`.
Tested code remains FW6e561ee5/HDLf16dc564 and parent660PASS25.11s; final agent
already-running repeat74096 terminated0,660PASS25.21s. Collector-only failures
(symlink executable, executable size, oversized duplicate-trace selection) stay
explicit. Earlier repeated public traces remain local with portable hash/size
receipts; all final traces, logs/XML and simulated sources are included. No
numerical/runtime changes or extra actual FFT execution occurred. Combined60
harness work proceeds separately; repeated unchanged suite runs solely to
qualify packaging revisions are not required.

## Next timing candidates: independent replays and C1 actual launch

Parent fully read the final CDC actual-preparation helper, observation-only
include, tests, report and frozen Tcl runner. Independent101 tests PASS16.65s,
original76528 terminal0, `/tmp/starlink-cdc-prep-parent.Wyx7P7`. All48 prepared
members still match inventory
`9c81c43d9ed0bbc6cfba1d40074d11ec8cd94530fc9d7920de809bd6d68ce39c`;
the project was absent before authorization. The seven direct runtime modules
remain identical to reviewed CDC runtime02de07cc. Parent independently verified
all1725 archive members directly from Git at HDL597a8ab65 (original23387 exit0),
manifest `0e1d4b836d244a21790704ec0a88a55c690788eb2378cad487a7d00a11b588d2`.

One R1D1S1C1/extras1/175/QUICK0 actual run is authorized at frozen
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1`,
FW4d59ce832f82fd06b8c95a1b2c2461a6162ecdb6 /
HDL597a8ab65ce9d4ee68b4ca0fe4a98ab48604beb7. Owner launched original20091
after all48 before-source checks. Use the original handle through terminal;
retain process status and after-source verification even on failure. Dec20
independent reference, all original numerical/CSV/stimulus and narrowly scoped
qualified-status rules remain unchanged. No C0 rerun, physical run, or radio
operation follows automatically. No C1 actual result is claimed at this checkpoint.

The separate local first-admission candidate also passed independent349 tests
in53.31s, original91543 terminal0,
`/tmp/starlink-local-admission-parent.txG0Cf`. Parent read its final strict recipe,
191-line bench and complete report; default-off additive guard/top and all old
runtime remain unchanged. The local enable removes current metadata logic only
from initial descriptor/job-started capture; it adds no logical state or latency
and preserves current beat/fault/certificate logic. This is offline equivalence,
not measured timing improvement. Its last actual route remains FAIL−1.341ns.

At FW1086dbf361a51c48ab6f9b2e8724326d4d802beb /
HDL461eda9fd2bf67a975f6016f06a8be789af9f077, parent read the tar and inventory
from Git and independently verified all6578 safe regular members and exact
archive SHA `203760ef6a3c7d781b001c54f4b67dbb8422177f0786e181e087e230277aef77`.
Offline actual-equivalence preparation is authorized for R1/B1/O1 plus this local
enable only, preserving old119-bit product/current fault/numerical checks and
adding the independent old guard comparison. No D/S/CDC union or vendor/physical
execution is included. Future canonical promotion remains separate.

Parent also read the complete frozen combined60 machine recipe and75-line
explanation at FWdd266118c2a524dec65c139076898098ea1563c6. It preserves the
immutable69 numerical files and original native service limits, permits only
the explicit startup pause outside the13312-sample continuous segment, and
requires independent enable/STOP ledgers plus every visible FFT/pilot/native
value. Additive combined harness/parser preparation continues; no combined60
actual, capacity, physical or RF result is claimed. Radios and PPU are untouched.

## C1 actual PASS independently verified; physical preparation next

Original20091 terminal0 with post-integrity0,10:47:42.315817530 through
10:57:22.768161867 UTC,580.44s. Parent read the full terminal sequence and
independently replayed frozen `verify_result` plus all four complete CSV hashes
and line counts (root74812 terminal0). Both main589950-line CSVs remain25ab9d06;
both extra33180-line CSVs remainb965d126. All48 sources and inventory9c81c43d
remain unchanged. Original qualified accounting is still1246258=953795raw_equal
+292463invalid_only, explicitly NOT original raw217 equality.

CDC observer reports712146 checks,8958/8686 destination-stage-high samples,
4675 reset-low samples,7882 current-fault edges,115 aggregate-fault/index511
samples and4265 private-core-reset-low/faulted samples. These are not distinct
injection/reset counts. Original independent final-fault2 and both exact
extra2fault/3stall/2reset/4recovery receipts remain unchanged. Nominal interval
maximum4548 and44 healthy blocks are retained. This establishes digital
actual-core equivalence, not analog CDC or timing closure.

At FW56c3105ba6a32fe973d36b760082ec477efc0d20 /
HDLc8321c4576d65c402d47bf8a3b6bdd66b90ce211, parent read the complete report
and independently verified all91 committed archive members (exact92-file closure),
manifest `e60f50a0c8e1f01f787f7ae67d7a2d83b4c1c5d04b3ad655c0eb011b021334cd`.
Parent additionally decompressed all13 archived log/CSV gzip members directly
from Git and checked every raw identity against live original files. The three
Git WDB parts reconstruct112102920 gzip bytes and122136408 raw bytes, SHA
`6814cf9dfab867e3715f1c55f74c3196f78711b64f6fabd7125e692763aaca3d`.
The generated-cause forward-reference warning remains explicit; simulation
does not establish synthesis support. Offline C1-specific physical preparation
is authorized with exact passing sources and unchanged100/175 constraints,
IP/directives/two threads. Synthesis and routing each require subsequent review.

## Isolated ROM read-ahead prototype: exact visible retention

Root created FW/HDL `codex/starlink-rx-only-do-not-merge-rom-prefetch` in
`/tmp/starlink-rom-prefetch.j829ht/fw`, based on control FW4d59ce832/HDL597a8ab65.
Only a new kernel variant and standalone bench are added; canonical modules and
callers are untouched. A private synchronous ROM read uses original input_ready
instead of the current metadata-qualified acceptance. A registered selector
and retained last-visible word preserve every old raw coefficient bit on healthy,
invalid, stalled, reset and fault cycles. All old acceptance/error/validity/history
logic remains literal under a strict whole-source recipe. At D18 this adds37
logical bits and a36-bit mux, zero nominal cycles. Mapped cost and timing are
unmeasured; selector/mux paths may need further work.

Initial52746:25PASS/1FAIL5.23s, `/tmp/starlink-rom-read-ahead-v1.jICW4m`.
The failing test misclassified another valid speculation enable as a semantic
mutant. Both input_valid and input_ready cover every acceptance; the first
still carries the metadata path. Retain that observed equivalent variant as a
positive control, use a genuinely missing-read mutant, and retain initial code
at FWcaf9f92fc/HDL0fe2ca5f5. No runtime repair was required. Two explicit-check
lint findings were fixed. Second9500:27PASS5.15s. Final15568:149PASS27.76s,
`/tmp/starlink-rom-read-ahead-final.76jGL7`, with one continuous512-beat block,
two stalled/bubble blocks, all64 identity-bit faults, accepted X/Z metadata,
20,000 explicitly unconstrained inputs per configuration, nine semantic mutants
and unchanged control/payload/retirement/CDC regressions. All12 width2/18/24,
balanced and scratch combinations compare original/default/enabled fields
unconditionally. This is standalone digital proof, not actual bank or formal
exhaustive verification.

Final FWd6ca47ef934a082b737191e3e41ca79e393d03cc /
HDL1dd76119a681b5aa0b6d9f0d5f5d32f974e81342. Parent verified all2333 committed
tar members including the embedded receipt, SHA
`b0c2c425cecfe6fd26ea784a2096c4146198a43f638c3e3c0bba4595dc71b660`.
All three attempts' logs/XML/generated source/executables are retained;
only48 redundant pytest current symlinks are excluded explicitly. Collector
integrity is not part of the149-test qualification. Separate report:
`/tmp/starlink-rom-prefetch.j829ht/fw/docs/starlink-rom-read-ahead-offline-20260910.md`.
Independent review and actual joiner/bank integration are still required; no
arithmetic/CDC/local-enable union, timing benefit or release is claimed.

During pre-evaluation combined60 review, parent caught a scalar receipt count
of520 where nine one-off markers plus512 pilot rows require521. Agent is
replacing it with an explicit marker inventory and negative tests, retaining
all native numerical/service limits. Parent also identified lexical-symlink
admission gaps in new local-enable preparation; corrected sources will be
separately frozen/tested without overwriting the unlaunched original bundles.
These are preparer/verifier corrections before vendor evaluation, not changes
to radio code, signal goldens, or acceptance thresholds.

## Local first-admission actual preparation independently accepted

Parent read the final362-line preparer/verifier,506-line tests, complete155-bit
original/default observer and binding include, frozen runner and diagnostics.
Independent121 tests PASS5.91s, original72855 terminal0,
`/tmp/starlink-local-actual-parent.PzGP6P`. Lexical aliases are now rejected before
Python/Tcl normalization, including dangling and ancestor/source/manifest aliases.
All original stimulus, two119-bit product observers and current fault/latency
checks restore exactly. The new observer derives its independent guard from
actual input ports, not candidate predicates; no epoch/valid/fault mask applies.
Mocked collector histories remain explicitly not actual execution evidence.

Parent executed the frozen verifier on L1-v2:45 files,19 compiled,8 runtime,
manifest `a84e723cb3de7b2c3382dbc88b89b6edc533d7493856540d1871d4ecd31831d5`,
runner `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`;
project and launch receipt were absent. Tested FW5c479ff19740e473501d90353cd0c376bec20d15 /
HDLe0e075d72711e27a866bdadebc1c14ef19c58326. One actual R1B1O1L1/175 execution
is authorized from `bank-arithmetic/hdl/library/starlink_pss_acquisition/build/
local-admission-actual-R1B1O1-L1-175-prepared-v2`, using the exact manifest,
SuSE2022.2 loader, two threads and original-handle ownership. Preserve process
status and after-integrity on failure, original11 receipts/76 jobs/19456 ordered
words per stream and historical candidate CSV e7127798. No L0 execution,
D/S/CDC union, synthesis, route or radio operation follows automatically.
No actual result is claimed by this preparation approval.

## First local-enable actual: diagnostic failure before time advances

Original22656 exited1,27.525s,11:10:48.649453 through11:11:16.174700 UTC.
Parent read the exclusive owner wrapper, original terminal, outer log and
simulation log. All45 sources plus manifest remain unchanged; after-integrity0.
`simulate.log` contains only `Time resolution is 1 fs`: no healthy block,
numerical event or guard comparison ran. The final missing-FFT-terminal error
is downstream of the actual cause: `LOCAL_GUARD_WAVE_PATH_MISSING actual_view`
in the new diagnostic Tcl before its unchanged `run all`.

Parent independently read original arithmetic diagnostic inventory: Xsim used
the escaped root `/\\tb_starlink_pss_local_admission_actual(FAST_MHZ=175,B=1,O=1,L=1) /`.
The new lookup hardcoded a plain unparameterized root. Existing recursive
arithmetic recording found115 objects correctly. This is not an arithmetic or
equivalence failure. All original sources/project/WDB/logs are preserved.
Authorize only an offline correction to additive discovery/verification:
collect exact observer/leaf suffixes recursively, require all14 unique with the
same allowed actual root as arithmetic evidence, preserve the real recorded
paths, and test real escaped/plain roots plus mixed/wrong/duplicate/missing
paths. No RTL, stimulus, comparison, debug/generic, latency or existing assertion
change is authorized. A new frozen bundle requires separate actual approval.

Parent also independently replayed29 C1 physical-preparation tests in31.12s
(original26713 terminal0, `/tmp/starlink-cdc-physical-parent.ZMmRil`), then read
the entire frozen synthesis adapter and unchanged external owner. All18 prepared
members match `66001eba6a4bd5773f73ea1eaac9b730cd11e620900bbce072b1b0c5d0accb65`;
settings explicitly select R/D/S/C1111. Full combined60 new-only offline scope
independently passes311 tests in5.83s (original92837 terminal0,
`/tmp/starlink-combined60-parent.d9y4WZ`). Its complete source review is still
in progress; no combined60 vendor execution is authorized by these test counts.

## C1 synthesis accepted; one diagnostic route launched

Original3292 synthesis terminal0,116.863291s,11:17:10.832780 through11:19:07.696160
UTC. Parent independently verified the committed56-member archive at HDL
096ab760b91198e8101614ed8b712f44f74707e2, manifest
c1b5e9210497458e6524b7abd8d8efb29485e22392613e83dff97d36a428d12f,
then rehashed all8 live synthesis products and13 copied/source/generated-IP
inputs. Owner before/tool/after/overall all0, zero black boxes. Isolated counts
1986 LUTs/4500 FFs/21 DSPs/15 RAMB18s: +16 LUT/+22 FF versus prior111 synthesis.
All12 per-cause synchronizers are recognized as depth2; CDC-10 is absent in
this report, but139 CDC-15 mailbox warnings and114/124 external I/O coverage
gaps remain. This is not a routed timing, full CDC or receiver qualification.

Parent read unchanged route Tcl in full and verified SHA
0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a.
One diagnostic route of exact checkpoint
8c87cbd93869a376ca727c601b47dc36ff6bc480e359abca5f12f3988ba426bd
is authorized with unchanged100/175 constraints and two threads. Agent owns
original49744, output `/tmp/starlink-completed-input.5EaJuD/fault-cdc-route-v1`,
separate exclusive owner `fault-cdc-route-owner-v1`. No retries or waivers.
Source checkpoint/script hashes must be checked after termination even on failure.

## Corrected local-admission diagnostics independently accepted

Parent reviewed full helper/test delta and complete frozen diagnostic Tcl and
runner. Independent143 tests PASS7.04s, original23760 terminal0,
`/tmp/starlink-local-wave-parent.B4icQu5u`. These include literal original115-path
escaped-root fixtures, complete mocked Tcl to the unchanged run-all trap, and
negative mixed/duplicate/missing/wrong-profile paths. Policy proves all compiled
runtime, observer, bench, numerical and runner bytes unchanged from failedv2.
Frozen standalone verification from `/` passed L1v3's46-source inventory,
manifest ae2173b877d75fc6f97246e612415e9c33a1f9d0215a6e5b1d3eb49bf6ae2f22.
Tested code FW6951006e63997f63f6f3bf0cd73cb4e5cea66b65 /
HDLe0e075d72711e27a866bdadebc1c14ef19c58326; runner remains f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98.

One actual L1/R1B1O1/175 run of this exact v3 freeze is authorized. Original14041
is owned by the arithmetic agent; exclusive owner `local-admission-L1-175-actual-owned-v2`.
Only four substitutions to the prior owner are allowed: preparedv3, new owner,
new manifest and45→46 source count. Preserve original22656 failure, all existing
functional/numerical/WDB gates and terminal/after-integrity receipts. No L0,
control/CDC union, physical promotion or radio operation is authorized here.

## New route and actual results: failures retained, not promoted

C1 route original49744 terminal0 completes all6736 routable nets without route
errors, but setup timing FAILS: island175/global WNS-1.830ns; global TNS-673.636ns,
653 failing endpoints. Island alone has535 failures/TNS-583.930ns. Hold+0.058ns
with zero failures; recovery/removal+0.615/+0.752ns. CDC remains0critical,
17information and139 unwaived mailbox warnings. Parent directly read the routed
receipt, timing-summary tables and full worst-path report. Worst path is held
phase→product metadata selection/checks→input_fault_now→descriptor capture CE:
7.291ns total,2.083ns logic/5.208ns route,71-load final enable. This supports
evaluating the separately tested local first-admission cut, not claiming the
CDC change has closed timing. No route retry or receiver promotion.

Local actual14041 terminal1,28.0999s,11:28:49.030957 through11:29:17.130980 UTC.
Parent read original terminal and simulation log. All46 sources plus manifest
unchanged; both diagnostic inventories now succeed, so the original discovery
failure is fixed. The new guard observer instead fails phase0 at time0fs,
iteration1, with unknown reset/start/metadata and differing155-bit views.
No healthy FFT job or numerical event ran. Root requested read-only field-level
and initialization/event-order diagnosis from preserved artifacts; no masking,
changed comparison or retry is authorized. Original22656 and14041 remain FAIL.

ROM read-ahead independent review identified missing directed healthy occupied
X/Z-ready and selector0/1-flush witnesses. Root added checked preconditions,
retention/stall/drain/refill assertions and four missing-case negative tests,
with runtime and unconditional old/default/candidate comparison unchanged.
Changed standalone suite31 PASS6.91s (original3382 terminal0),
`/tmp/starlink-rom-active-boundaries-final.59q91XWV`. Earlier25PASS/2FAIL illegal
parameter-fixture elaboration attempt and subsequent27PASS are preserved.
This extends standalone coverage, not the earlier149 combined-test claim or
actual FFT/physical qualification. Full details in the isolated ROM branch's
`docs/starlink-rom-active-boundaries-20260910.md`.

## First paired60 actual launch approved after complete source review

Parent completed review of the final206-line result verifier,93-line vector
preparer,222-line bundle helper,91-line Tcl runner, CLI, all579 lines of three
new test files and final preparation report. The268-line top and178/134/65-line
source/FFT/clock includes had already been read. The original native verifier's
complete-function AST projection retains every inner numerical/service check;
only eight enumerated outer-context changes admit paired receipts. Nine singleton
paired markers plus512 pilot-word lines require exactly521, independently of
the60 native-component markers. The full bench checks every emitted FFT/filter
prefix, not just summarized counts. The311 independently repeated offline tests
remain preparation, compile-only and verifier evidence, not actual simulation.

Parent ran the frozen snapshot CLI from `/`: bundle
b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714 PASS,
source signature26f33d8727828eabd56d24466984168be3bdc52fc5e0166ba8ffe94f0e89b8e8.
All108 live source hashes match the frozen source. Committed archive at
FWb47c355b08cf66af126f173093cf90b4928fca99 was independently verified:334 safe
regular members,333 exact member hashes/lengths plus embedded receipt; archive
60980bcc984b4c4b396de4429d95cb79d4b62d2a52b291552d402316af7f8f20.
HDL88195cd9029a0c66f642fe21045ff70053fc46de and FWb47c355 are now root-pushed
to the high-rate60-paired DNM remote branch.

One exact healthy60upper/ideal100-175/native264/PIL1/447x2 actual run is authorized.
Frozen runner c8233d7200a7dbbefe1ac5644350101ebc70784151095cfb3166e290cbaa471d
uses reviewed2022.2/SuSE environment, two threads, explicit repository Python
and log/journal arguments before Tclargs. Agent owns original5432; new run
`/tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1` and separate
`main-high-rate60-bank175-447-v1-owner`. All output/owner/external log/journal
paths were checked absent. Require original process terminal, immutable external
bundle and copied inputs, generated-IP before/after hashes, full strict result
verification even when compilation/simulation fails. No retries or source edits.

Acceptance retains the original69 golden files,264 taps/520 native capture,
257 raw/241 qualified tuples, full public52-word repeated readout and full drain,
both exact decimator ledgers,512 pilot CI16 words and actual overlap. The original
16423 samples include an explicitly declared startup pause; only the subsequent
13312-sample segment is wall-clock continuous60. No added tail, causal acquisition,
production20k maps,750 measurement/s, DMA/IIO throughput, physical60 or RF claim.

## Local startup diagnosis: proposed scheduling proof, no waiver

Read-only field decode narrows the14041 diagnostic difference to mixed-X nibbles
103:100 and3:0. A sufficient source-based hypothesis is actual core_input_tready0
while the observer's copied input remainsX during time-zero alias propagation.
The hexadecimal log cannot identify each differing bit or exclude a real state
difference. No proprietary WDB loader was invoked and no benignity claim follows.
An offline bounded hierarchy/scheduling reproduction is authorized, including an
original-RTL-as-DUT control and true pre-NBA/current-fault/reset corruption tests.
Proposed #0 before PRE comparisons would settle Active-region combinational
aliases without advancing time or intentionally skipping NBA state; it must be
demonstrated before adopting any observer change. Every clock/reset event,155
bits and existing1ps POST observation must remain. No new vendor run authorized.

## Paired60 actual PASS, independently verified without rerunning simulation

Original5432 terminal0. Genuine HIGH_RATE60_PASS and unchanged frozen result gate
HIGH_RATE60_SIMULATION_VERIFIED; run_tcl_exit0/integrity_exit0 and terminal receipt
present. Parent independently reran the frozen snapshot CLI's result mode from
`/`, terminal0, and obtained the same complete result as the original receipt.
Both original and copied250-file bundles match b5f7d48a... with no missing/extra
files; generated vendor wrapper still matches its recorded pre-run SHA
a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68.
Standard Wavedata display warnings are retained in outer Vivado output, not the
actual simulate.log; the existing strict warning/failure rejection passed
unchanged. No parser correction, source change or retry was needed.

Measured exact prefixes:894 visible/admitted scores and447 map words;
1536 forward-input/forward/product/inverse-input words and1024 inverse outputs;
894 numerator/ratio preparations. Both independent decimator ledgers agree:
14518 enabled raw inputs→7251 first-stage outputs/7250 second-stage admissions
→3618 canonical outputs. Pilot3617 admissions/mixed,1808 halfband outputs,
602 full outputs,512 selected/exported CI16 words/2048 bytes with exact indexes.
These are bounded prefix counts, not all seven frozen golden FFT blocks.

Native admission at index34359738591, lead1664, controlcycle10678 versus
trigger10625. Snapshot capture10627/return10639, captured34359738559,
capturelag2/returnlag9. All520 capture coordinates and264 coefficients feed
exact257 raw/241 qualified results;52 public packet-word reads match twice.
Capture ends14318, publication86814, publicrelease87604, finalrawdrain88959:
72496/73286/74641 cycles after capture respectively (724.96/732.86/746.41us
at simulated100MHz). All257 results are required even though publication occurs
after249; maximum tuple hold11, AXI8,105 readout transactions.

Actual FFT-input handshakes during native capture245; native compute overlapping
coarse/pilot5671 cycles and after STOP67405 cycles. Source off32415 after16423
original plus2 prime samples, native still busy;56544 compute cycles follow
source-off. Map retention survives native release, both public releases occur
after source-off, and final256 quiet cycles end89576 with no stale result.
STOP occurs after9908 total source samples, while independent pilot/native work
continues. This establishes healthy digital composition, not deployment:
known center, ideal clocks/direct AXI,447x2 reduced map and declared startup pause.
Routing/CDC/I/O closure, causal scheduling, full production service, host IIO and
actual60 RX calibration remain open. No radio was accessed or changed.

Publication check also completed for local-admission history at FW
a3c691ffc12a10c3742c40f118e9cf391c167c1f: root directly verified6662 preparation,
179 original22656 failure,2574 diagnostic-correction and184 original14041 failure
archive members from Git objects (first archive reconstructed from two exact
parts). All lengths/hashes/exact safe member sets match; all failures retained.
Reviewed FW/HDLe0e075d are pushed to the bank-arithmetic DNM remote.

## Local admission actual6473: independent parent verification

The observer-only settled-pre-NBA correction at FW8130a750734c6fd9fc8cedb4131cfa9e56b71d22 /
HDL62da6a39edb8e40e08d41cbb13ba04af7584842d independently passes188 tests in7.88s,
original98004 terminal0, retained at `/tmp/starlink-local-schedule-parent.BDQZlu7W`.
Only two #0 waits precede PRE checks; all155 bits, events and +1ps POST checks
remain. The offline original-as-DUT counterexample demonstrates a sufficient
alias-ordering mechanism, not the exact vendor cause of original14041.

One authorized actual6473 completed at12:01:46.110204UTC,234.513s, process0,
run_status0/after_status0, with49 frozen sources plus manifest unchanged.
Parent reran the exact frozen result CLI from `/` and obtained the same result
object as original results.json: all11 old terminals,76 original core jobs,
19456 ordered words per transform stream,16986 output-derived oracle-only
scores, complete historical CSV e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71,
event CSV7bbe79fd2648984f0901296d69c1e168cac400426eb2642e91e24ff3815803f3.
This does not execute scorer RTL or prove physical timing.

Guard observations are pre1180132/post1180131/reset256,150 forward/71 inverse
starts,17 current faults,897 sticky faults,320098 completion checks,13859 closed
prefetch checks and2 duplicates; all155 bits unmasked, zero added latency.
The final clock's +1ps and $finish share a physical timestamp; the unconditional
final compare executes before $finish. The one-counter difference is explicitly
retained pending saved-history review, not asserted equal or explained away.
Read-only WDB extraction and offline L1 physical adaptation are authorized;
no simulation restart, synthesis, route, union or radio action is authorized
by this checkpoint.

Parent directly verified Git archive closure at FW75c8e044cefe5e8ad8fa3f88997436d405107746:
four parts reconstruct144578850 bytes SHA80b06a8826ebc180324c1f16ccb4f2552f6d028f14fc8086a3916422fb139857,
all189 safe regular members match exact lengths/hashes. Preparation4197 members
at FW9d1bb7c732ee39a98b0ca799d0abcd7a9874ed77 also verify,30683393 bytes,
SHAb8585feb1c71fa0beb4240700d3611fa55b32f1d270cce69076f76910811397f.
Original22656/14041 failures remain unchanged.

## Word plus metadata prefetch: independent offline and publication gate

Root repeated the final suite at FW4e61c9dbda24a4a437f1d00b596c366edd267b3b /
HDL32b20cb750caeede27561193728f088bc249195e:60 PASS16.10s, original72716 terminal0,
`/tmp/starlink-rom-metadata-parent.WaYEp9Z4`. This includes31 old word tests and29
new tests, unconditional old/public coefficient, metadata and state comparisons,
four option combinations, current faults, unknowns, stalls and reset/flush.
Metadata prefetch moves the current-validation dependency from69 capture enables
to a retained/speculative selector in RTL, with+70 logical bits and no new cycle.
Mapped critical-path removal is unmeasured; word-only prefetch does not target
the separate measured block-metadata enable path.

Root verified all836 safe Git archive members (835 source/artifact entries plus
embedded receipt) at FW03ba61b4decf7a41cc0a0d1e83f3cdfaff6d8a69,4113301 bytes,
SHA10390700c7d77202e35ae3b1d3fb019e5a62fc67bb42ca12687d795895e1b8fe.
Five final changed-source bindings match the tested FW/HDL objects. Initial
read-only parent archive checks assumed the other archive schema (members map
and plural receipts filename); those diagnostic checks failed before correction.
The exact singular receipt.json/count schema was inspected and fully verified;
no archive bytes, tests or simulations were changed or rerun for that correction.
The first parent local result command also tried the unrelated run_status.txt
name after successful result equality; actual run_outcome.txt was then read
directly and reports both zero statuses. No original run was restarted.

Offline additive joiner/bank integration preparation is authorized in the ROM
worktree, with the accepted C1 seven runtime files byte-identical and original
stimulus, numerical CSVs and fault gates retained. No actual or physical launch
is yet approved. Healthy paired60 final evidence at FW7c62a3382baef4b922cec92c1e71c0fa67061970
was already root-pushed: compact286-member archive SHA
c2118ae7a34231c86be5e13e2e857e570bae9844162686c3414243dc1ff8c5b6,
plus independent parent checks of all544 raw-run files/64345759 bytes.
The next paired60 negative has a frozen late/expired-command recipe before
evaluation; healthy runtime, source and golden data remain unchanged.

No radio, PPU or deployment state changed. Full receiver timing/CDC/I/O,
calibration, causal acquisition, continuous host service and RF verification
remain necessary; neither arithmetic equivalence nor archive closure replaces them.

Reviewed publication completed: root pushed FW75c8e044/HDL62da6a39 to the
bank-arithmetic DNM remote and FW03ba61b4/HDL32b20cb7 to the ROM-prefetch DNM
remote. All four original push commands exited0. No firmware-main push or
primary runtime gitlink promotion occurred.

## Read-only recorded-history review completed

The single saved-WDB loader5578 exited0 in8.022s, with no simulation advance.
Root read the exact Tcl and owner, then independently rehashed all11 inputs
against before/after receipts, including unchanged130MiB WDB
52f4ccf572df859e21cdb6e92a82c3b22459b551874acf241f0ea8acd7539a31.
Root independently parsed2193 unique recorded values:115 arithmetic plus14
observer paths at17 physical timestamps. Every actual/original/default155-bit
view matches, including the mixed-X startup values. The original physical
snapshots are evidence of recorded history, not merely selected wave paths.

At0fs counters are pre1/post0, at1000fs1/1; the first subsequent edge is2/1,
then2/2 at+1ps. Immediately before the final edge counters are1180131/1180131;
at the edge1180132/1180131, remaining so at the exact final+1ps/$finish time.
The outstanding final counter increment is directly localized by these saved
values. This finite sample set does not prove every prior edge independently,
resolve intra-timestamp Active/Inactive/NBA ordering, or retroactively explain
the prior14041 failure. Those limits remain explicit.

Raw read-only extraction is retained under the arithmetic worktree's
`hdl/library/starlink_pss_acquisition/build/local-admission-wdb-history-v1.7RQSIW`.
Tcl SHA05d9b02626d2849b4b18bd8c0dfd533d2a102e0fb874a9ffaaeefa9d3a60b7fb;
owner SHA3d59d459dcf4e75f28339722c33f85a0e16beefbe7127645983bdbf0e1247a07.
No new actual simulation or physical evaluation has run. The next bounded work
is the source-specific L1 physical preparation and ROM/late60 integration tests.

## Interim ROM integration review: stronger inherited-source admission required

The first additive C1 ROM integration draft passes76 offline tests in3.50s
(agent-owned original17052 terminal0). Root reviewed the264-line helper,
96-line observer,96-line real-joiner/ROM fixture and277-line test suite before
any vendor launch. Full C1 hierarchy tests are compile-only; the separate
executed fixture uses real ROM/joiner RTL but no vendor FFT or bank lifecycle.

Review found that verify_prepared bound seven canonical RTL files and the
top/runner inverses, but trusted a rehashable new metadata map for the other
inherited C1 observers, references and helpers. Root requested a pinned original
C1 inventory and full inherited-file/in-memory-inverse comparison, with
rehashed old-observer/reference/helper negative tests. The first passing draft
is retained, not relabeled as the corrected gate. Root also questioned allowing
zero sampled private-reset edges: the new predicate includes the accepted C1
faulted-private-reset observations, so zero is unjustified for the planned run.
The corrected gate must require positive coverage and preserve its distinction
from reset-event counts. No actual or physical launch is approved for this draft.
