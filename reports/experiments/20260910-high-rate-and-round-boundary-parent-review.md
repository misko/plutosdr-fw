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
