# Independently registered guard facts — DO NOT MERGE

Based on private-certification FW `eda2c6dce` / HDL `cf4b70230`, the best prior
measured subsystem reference (-1.452 ns WNS / -451.168 ns TNS / 704 failures).
New branch: `codex/starlink-rx-only-do-not-merge-guard-facts`.

## Change and contract

Each guard adds an eight-bit output containing its existing offered local fault
facts before OR reduction. The original scalar output and all current-fault
handling remain unchanged. The admission certificate replaces two compound
guard-fault bits with sixteen individual bits: 22 checks become 36. Completion
likewise grows from 28 checks to 42. Original non-guard checks, request timing,
quarantine, one-shot consumption and public permissions are unchanged.

The new vector is zero when offered summaries are disabled, exactly matching
the old scalar view. No check, clock stage, immediate publication veto or
reader-ACK condition is removed. The intent is to register smaller predicates
before reduction, not to weaken or delay the aggregate fault condition.

## Executed functional verification

Complete source inverses verify that the guard and top differ from their pinned
parents only in fact export/expansion and certificate wiring. The source-extracted
four-state comparison covers 1,048,692 cases: every eight-bit four-state pattern
in either guard with representative other-guard reductions, enabled/disabled
operation, plus non-guard fault bits and admission/completion availability.
The expanded rejection OR and both checks-good ANDs are exactly equal to their
original forms. Three unsafe exports (dropped fault, ignored disable, erased
unknown) fail. These five tests plus four private-certification tests pass in
10.58 s. The historical private-certification inverse now uses its pinned
snapshot and requires the live expression to remain identical; the new complete
top inverse proves the current additional changes separately. No gate test is
removed. Two source/lint preflight checks pass.

Actual generated FFT passes in 156.56 s, with all 64,512 records independently
matching and the CSV byte-identical. Service remains
3659/3659/4927/11727/3659/3659 clocks. The deliberately stalled reader has no
5215-cycle claim; other contexts pass that unchanged bound.

Real 22/28-bit legacy certificate instances observe the same request, quarantine
and consume signals as the 36/42-bit candidates. Every live clock checks current
aggregate equality and, after the edge, exact permit/snapshot-valid/consumed
state and compressed snapshot contents, including X values. These witnesses
authorize nothing and are present only in the simulation bench. All 384,922
checked cycles agree. The full prior numerical/fault/reset/ownership campaign
passes, followed by 32 independent fact injections: each of eight guard facts,
in both owners, at each admission/completion snapshot. Each fact is observed in
its own stored bit and the old aggregate bit, with known quarantine and no
start/read/release for 100 clocks. The injections target the summary vector to
verify mapping and capture; prior fault cases exercise actual event sources.
A final fresh reset/block produces 512 correct reads and one real release.

Source-matched synthesis passes in 96.69 s. Before/after source checks pass.
This remains a subsystem test, not continuous native reception or board signoff.

## Route and regression: mixed result, still FAIL

464 combined regression tests pass in 68.22 s, including ten new evidence-parser
controls. Missing/duplicate fact cases, missing terminal evidence, low coverage,
stale starts/reads, disabled equivalence and incomplete recovery are rejected.
Actual FFT, synthesis, route and all test runs pass on first invocation. Route
completes in 60.47 s. Independent source/checkpoint/report audit passes.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private-certification reference | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |

Worst slack improves by 0.112 ns, but TNS worsens 12.468 ns and 117 more
endpoints fail. This is not an overall improvement or deployment promotion;
retain both references. 821/13869 setup endpoints fail. Hold +0.051 ns and pulse
+1.830 ns pass, with 8465 nets fully routed and zero errors. Resources:
2808 LUT / 5691 FF / 21 DSP / 15 RAMB18, zero RAMB36. Diagnostic 100/175 MHz
clocks and recipe are unchanged; no timing waivers added. Five critical CDC
findings, 208 warnings and 114/124 unconstrained board I/O remain.

The worst path now ends at output-bank request-toggle D: publication phase ->
metadata selection/comparison -> guard/current-fault checks -> actual bank
publication. Eight levels, 7.051 ns data delay, 5.603 ns routing. The next path
(-1.205 ns) ends at inverse guard awaiting-ACK. This is now a public ownership
boundary, not a private certificate enable that can simply ignore current faults.

## Next gate

Inspect the output bank's private-write/replay metadata selection together with
guard retirement and held ownership. Determine whether metadata can be prepared
and held before publication so phase decoding no longer feeds a wide comparison
on the publication edge. Prove exact first-word/final-word metadata, held replay,
and fault/reset behavior; preserve same-edge publication vetoes and real reader
ACK. Do not remove or delay the public fault check merely to shorten this path.
Compare against both retained candidates, and require actual FFT and route
evidence before accepting a composition. No new receiver features before closure.

## Evidence and deployment scope

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-guardfacts-{prepared,actual,synth,route}-v1`, and
`staged-guardfacts-{unit,preflight,regression}-v1` with XML receipts.
Inventory: `03bf519fbf39f8142e00861b7ac942b7e531afb07267a6965d89a88b977d5776`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Original top: `6c181d830143c998ffa3fba15d51fe34cf087d08eb622591f698229b07b1a4a4`.
Original guard: `6b3f4ff240f3f81edaaf694f7b2a926be320da71bfc3641d84a6ce3c87104f45`.
Synthesis DCP: `015edd7a3ff1d9472958657d068bd4115ea205362b6f88ef93321bc828e0a3c4`.
Routed DCP: `ab681d26848908f8a5454479611d14a74040ee00fafeff525f6b074ee71f287e`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
required. Subsystem timing/CDC and full receiver route/reset/board I/O,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO verification
remain before `.18` reversible canary, then `.17` PPU Ethernet-only deployment
with pinned rollback. Final verification remains 300 seconds, 120 ms valid
dwells and blind host GLRT comparison. No radio, PPU, main or primary production
HDL changes were made in this experiment.
