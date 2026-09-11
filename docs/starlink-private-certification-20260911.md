# Private descriptor certification — DO NOT MERGE

Based on private-kernel-sequence FW `74c1e2b67` / HDL `f4e14c326`, which passes
actual FFT and 435 tests but routes at -2.047 ns WNS / -550.201 ns TNS / 825
failing endpoints. Branch: `codex/starlink-rx-only-do-not-merge-private-certification`.

## Change and contract

Only one runtime expression changes. In VERIFY_LEASE, descriptor_certified now
captures `preparation_valid && (CERTIFIED_ADMISSION || !any_fast_fault)`.
Certified admission therefore stores a private preparation snapshot, without
the repeated global current-fault OR in its register input. Non-certified
admission retains the original `preparation_valid && !any_fast_fault` expression.

The later admission request still snapshots the original current rejection
facts. Its permit, receipt consumption and input-job token remain fenced by
registered epoch quarantine. Fast faults and detailed reason banks still latch
on the current edge. Publication retains its immediate current-fault veto.
No descriptor check, public authorization, clock stage, or FFT arithmetic is
removed. A private snapshot on a fault edge must not start or configure a job.

## Executed functional verification

Four unit tests pass in 0.04 s: complete source inverse against the pinned
parent, a 32-case four-state expression/fallback table, and two rejected unsafe
expressions. The inverse verifies all other runtime admission, quarantine and
publication logic is byte-identical. The table is expression evidence only,
not a full admission proof; the actual FFT campaign covers integration.
Two source/lint preflight tests pass.

Actual generated FFT passes in 133.25 s. All 64,512 numerical records match the
pinned reference and the CSV is byte-identical. Service remains
3659/3659/4927/11727/3659/3659 clocks. The deliberately stalled reader context
has no 5215-cycle service claim; all others pass that unchanged bound.

A clock-by-clock original-certificate model checks 318,097 live cycles.
There are exactly two private differences: valid descriptor snapshots on a
vendor-fault edge in forward and inverse preparation. Both have known asserted
quarantine and known-zero job acceptance/start/configuration/input afterward.
Six added actual cases cover those two faults, either outer reset at snapshot,
invalid starting position, and X starting position. Stale work produces no
start/read/release for 100 clocks. After each case, coordinated reset plus a
new input block produces 512 verified reads and one real release. The unknown
case requires retained nonzero-or-unknown preflight evidence and known-zero
public starts; it is not presented as a known binary diagnostic fault result.

All previous admission snapshot/permit/receipt cancellation cases and the full
reset/fault/ownership/capture/sequence campaign pass. Total receipts including
aborted and fresh-recovery work: 119 admissions and 90 completions. Synthesis
passes in 98.88 s; actual and synthesis before/after source checks pass.

## Routed result: best measured reference, still FAIL

449 combined regression tests pass in 56.53 s: 435 inherited tests, four source/
expression tests and ten actual-evidence parser controls. Missing cases,
missing/duplicate receipts, insufficient cycle/difference coverage, stale reads,
incomplete fresh output/release and absent consumption checks are rejected.
Actual FFT, synthesis, route and all tests pass on their first invocations.
Route completes in 58.71 s; independent source/checkpoint/report audit passes.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private descriptor capture | -1.969 ns | -813.676 ns | 914 |
| Private kernel sequence parent | -2.047 ns | -550.201 ns | 825 |
| Private descriptor certification | -1.452 ns | -451.168 ns | 704 |

All three measures improve versus both references. Worst slack improves
0.595 ns versus the immediate parent; TNS improves 99.033 ns and 121 fewer
endpoints fail. This is the new best measured development reference, not a
timing pass or deployment promotion: 704/13801 setup endpoints still fail.
Hold +0.070 ns and pulse +1.830 ns pass; 8350 nets fully route without errors.
Resources: 2744 LUT / 5668 FF / 21 DSP / 15 RAMB18, zero RAMB36. Diagnostic
100/175 MHz clocks and routing recipe are unchanged. Five critical CDC findings,
208 warnings and 114/124 unqualified board I/O remain. No timing waiver added.

The worst path now ends at completion_gate/snapshot_good[9]: publication phase
-> output-bank metadata mux/comparison -> inverse guard local fault summary
-> completion snapshot. Eight levels, 7.020 ns data delay, 5.572 ns routing.
The next reported path (-1.437 ns) ends at the inverse guard awaiting-ACK bit.

## Next gate

Continue from this measured reference. Inspect completion snapshot inputs and
inverse guard retirement together: a partitioned certificate still contains
compound guard-local fault predicates fed by bank metadata. Determine whether
those same predicates can be represented as smaller independent registered
facts, preserving their exact aggregate meaning and unknown handling. Keep
the final word/descriptor owned through validation and retain immediate bank
publication vetoes, reset cancellation and real reader ACK. Recheck actual
FFT/stall/fault/reset behavior and source-matched route before accepting it.
No extra receiver features or diagnostic clock relaxation before closure.

## Evidence and deployment scope

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-certification-{prepared,actual,synth,route}-v1`, plus
`staged-certification-{unit,preflight,regression}-v1` and XML receipts.
Inventory: `73770113445a26a7ee7589064071bb28192a76d35688a8737dfc9ac391c677c1`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Original top: `2df734a229635ef94cc1017ab1bba6d0bcdfad762655619c0e28fd68c80df68d`.
Synthesis DCP: `174267cb6bbb8e7c1becfdc3c2e7c0d30f7d4b53c54c151c034d17bc654a9cc8`.
Routed DCP: `5e388b0bd65cab4b5f703ecb019c5f53c1959595f22c7613febbe57f46a77ec6`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Subsystem timing/CDC, full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO verification
remain before `.18` reversible canary and `.17` PPU Ethernet-only deployment
with pinned rollback. Final verification is a 300-second scan, 120 ms valid
dwells, and blind host GLRT comparison. No radio, PPU, main or primary
production HDL changes; subsystem tests are not a deployed receiver result.
