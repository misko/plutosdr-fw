# Held output-bank metadata — isolated timing experiment, DO NOT MERGE

Parent FW `bf817a6bd` / HDL `82be254db`, expanded guard facts. Parent diagnostic
route: -1.340 ns WNS / -463.636 ns TNS / 821 failing setup endpoints. Retain the
private-certification reference too: -1.452 / -451.168 / 704. Neither is closed.

## Scope and acceptance criteria

Remove only the publication-phase metadata selection for registered scheduling.
Use `{inverse_tag, guard_return_metadata[1][4:0]}` for private writes and replay.
Inverse tag changes only on allocation/reset; no new inverse allocation is
permitted before actual reader release. Inverse return exponent updates only
on raw output while its guard is active; retirement makes that guard inactive
through ACK. The final value is already present on the first private bank-write
edge, unlike the top-level descriptor payload that captures a cycle later.
The original selection remains literal for nonregistered scheduling.

Keep all current fault diagnostics, same-edge publication vetoes, descriptor
validation, ownership and real reader ACK. A whole-top source inverse must
show no other runtime change. Four-state wiring/fallback checks do not prove
the ownership invariant; actual integrated simulation supplies temporal evidence.

A second real bank observes identical live inputs but uses the original mux.
Compare writer readiness, framing/sticky faults, cursor, request and synchronized
ACK, plus valid reader payload/metadata. On every accepted private/replay beat,
compare metadata case-exactly. The witness has no authority over the candidate.
Run it through the complete actual FFT numerical and fault/reset/stall campaign.
Require coverage of first/final words, replay, reader stalls and recovery.

Require all 64,512 numerical records unchanged, service latency unchanged,
combined regressions passing, and source-matched synthesis/route with unchanged
100/175 MHz diagnostic constraints. Compare WNS, TNS and failure count against
both references; a routed checkpoint is not a timing pass. No new features.

## Initial verification

16 unit/preflight tests pass in 10.66 seconds: complete top inverse, 1,184
four-state wiring/fallback cases, three rejected wiring mutations, prior guard
fact/certification tests and implicit-net lint. The historical guard-fact whole
top inverse now uses its SHA-pinned prepared top; the new whole-top inverse
checks today's metadata-only delta. No prior semantic check is removed.

Prepared inventory: `c26a6c00e91bfb2a484d91cfd9222ffdf3ead44ef51412530afab21e0ff3d878`.
Actual FFT passes in 154.31 seconds and source-matched synthesis in 96.07
seconds, both first attempts. All 64,512 numerical records match with identical
CSV SHA256 `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service remains 3659/3659/4927/11727/3659/3659 clocks. The deliberately stalled
11727-clock context is excluded from the 5215-clock diagnostic service bound.

The original-mux real-bank witness passes through all numerical, fault,
reset, quarantine and recovery cases: 385,028 writer-state checks, 53 first-word,
99 final-word, 46 replay, 16,374 valid/ready reader and 21,916 stalled-reader
observations. These are falling-edge observation counters, not a count of
unique completed frames or a continuous throughput measurement. Actual bank
state and valid reader data/metadata compare case-exactly. Existing source fault
and cancellation campaigns pass, including fresh 512-word/one-release recovery.

## Completed physical comparison: regression, do not promote

479 combined regression tests pass in 70.41 seconds, including ten new witness
evidence-parser controls. Missing/duplicate terminal evidence, insufficient
coverage of each boundary and a disabled bank comparison are rejected.
Route completes in 53.54 seconds; independent source/checkpoint/report audit
passes, but physical timing fails. All runs are first-attempt terminal successes;
successful routing execution does not mean timing closure.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts (parent) | -1.340 ns | -463.636 ns | 821 |
| Held bank metadata | -2.203 ns | -672.268 ns | 796 |

This saves 139 LUTs and five FFs versus the parent, and has 25 fewer failing
endpoints. However, WNS worsens 0.863 ns and TNS worsens 208.632 ns. **Do not
promote this candidate.** Keep both earlier references. Resources: 2669 LUT,
5686 FF, 21 DSP, 15 RAMB18 and zero RAMB36. 796/13863 setup endpoints fail.
Hold +0.072 ns and pulse +1.830 ns pass; 8264 nets fully route with zero errors.
Constraints remain diagnostic 100/175 MHz with no new timing waivers; 114/124
unconstrained board I/O, five critical CDC findings and 208 CDC warnings remain.

Worst path is now output-control phase bit 0 -> remaining private/replay
selection and bank framing -> inverse completion qualification -> output-control
phase bit 2. It contains 13 logic levels, 7.862 ns data delay (5.414 ns routing).
The next path (-2.086 ns) ends at inverse guard fault reasons bit 0, from the
registered scheduler phase. Removing the metadata mux alone does not remove
this phase-to-current-fault-to-control feedback path.

Next investigate the **complete private-write/replay handoff**: whether all
payload/position/last values can remain sourced from the retired inverse guard,
and whether its private-valid and replay-valid ownership are mutually exclusive.
Do not assume those invariants from the metadata proof. Check first/final words,
late raw events, stalled status/replay/readers, both resets and real ACK; compare
the actual original bank and controller observations. Keep all immediate public
fault vetoes. Route any composition before selecting a new reference. No added
receiver features and no clock relaxation merely to make this test pass.

Synthesis DCP: `afecf8050c27ddde9cd42d6057df1e0b56a9440a49b0cef5d481aad528ac5e33`.
Routed DCP: `24adc4a72cda88f9b5d1fdae69208eb538a15906643f0e603c2438cd933247fc`.
Evidence folders: `staged-heldmeta-{prepared,actual,synth,route}-v1` and
`staged-heldmeta-{unit,regression}-v1`, with XML receipts, under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Two packaging invocations rejected a missing campaign-version map and a repair
indentation error before creating any archive. The map and indentation were
corrected; tested RTL and all simulation, synthesis and route sources were
unchanged. Packaging read-back, not those failed invocations, is the archive gate.

## Required end state remains unchanged

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Subsystem timing/CDC, full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO qualification
precede `.18` reversible canary, then `.17` PPU Ethernet-only deployment with
pinned rollback. Final test: 300-second scan, 120 ms valid dwells, blind host
GLRT comparison. No radio, PPU, main or primary production HDL changes here.
