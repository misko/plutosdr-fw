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
