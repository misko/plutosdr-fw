# Integrated registered input identity — DO NOT MERGE experiment

Parent component implementation: FW `30afa5c0537decf78c5463662d1211fda22a48b4`,
HDL `569c1d59631126c1185d549c2cd50dcbb7af6c27` on
`codex/starlink-rx-only-do-not-merge-input-validation-stage`.
The earlier component-only document remains historical; this document records
the subsequent actual FFT integration. No production or radio changes.

## Implemented integration

Bank READY now means capture into the private stage, not FFT consumption. Each
accepted word and identity result are held together until the actual input
checker takes them. Offered-beat summaries now observe that same stage output;
certified input, result guard counts, completion and cutover still refer to
actual checked FFT consumption. The admitted descriptor is compared at capture.

A core-reset-scoped `staged_input_closed` bit stops prefetch after accepted LAST.
This prevents a following bank from entering the same job while its predecessor's
final word remains buffered. The existing engine input reservation is retained
until certified final consumption, not released by the upstream bank's LAST ACK.
Both stage and checker share the existing per-core reset. Stage control faults
join current input faults and the completed-input fault view; sticky quarantine,
publication veto, reader release and outer reset protocols remain unchanged.

Only the top changes among the original 17 runtime modules. Two new modules
are added to the frozen runtime inventory (19 total); the original, unused
checker remains compiled as reference. A complete top inverse permits only
staging, offered-beat rewiring and stage-fault propagation. A separate complete
checker inverse preserves all non-identity equations. This is a deliberate
transport retiming, not a cycle-for-cycle identity with the old input path.

## Verification so far

Preflight: 12 tests pass in 0.39 s. First broader regression: 487 pass, two fail
because historical tests still require a byte-identical top. The current delta
already has its independent full inverse. Historical guard-fact comparison is
now pinned to its parent; current guard-fact expressions remain tested. The
preflight test checks unchanged modules and live publication ordering while
the dedicated inverse checks the modified top. After those test updates,
**489 tests pass in 71.68 seconds**, no failures/errors/skips.

V1 actual generated FFT passes in 171.73 s, with source receipts unchanged.
All 64512 seven-stream numerical fields match the old reference exactly. CSV
SHA changes because this is a retimed execution; byte identity is not claimed:
`44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
Service: 3661/3661/4928/11728/3661/3661 clocks versus parent
3659/3659/4927/11727/3659/3659. Normal +2 clocks, backpressured cases +1.
The 11728 case includes the deliberate 9000-clock reader stall and is excluded
from the unchanged 5215-clock diagnostic service gate. No deadline extension.

An independent stage scoreboard checks occupancy, held payload/identity and
admitted descriptor on actual captures. V1 observes 74885 captures, 74883 private
retirements, 75031 held-valid checks and 146 buffered-final ownership checks.
Counts include aborted jobs and are not RF frame rates. Existing fault, reset,
publication pause and recovery cases all pass. Parent phase assertions still
run: 419227 checks, 3124 replay and 62 published/unread-preflight observations.

V2 adds six directed real-FFT boundary cases without changing runtime: wrong
and unknown identity in forward/inverse input at positions 7 and 511, plus
fast/slow reset while the final inverse word is buffered but not consumed.
Each requires no invalid FFT delivery/completion or stale publication and a
fresh 512-read/one-release recovery. The V2 audit requires all six cases.
Prepared inventories: V1
`f7b174267326f92800ee27b4cbd518def346fd1cd73dcd56b188b0b2bb051007`,
V2 `b8fa61a47a66e7363d67227a197176f8145e3764bcf97551769328ae68b28e66`.
V2 synthesis succeeds in 96.83 s, DCP
`8d4ffe35a99a79d2a59cc5a719263834c2b712aae24e292d7e3c11686bb51987`.
V2 actual FFT passes in **188.26 seconds**, all six new fault/reset boundaries
recover cleanly. All 64512 numerical records and V1 CSV remain exact; service
intervals are unchanged from V1. The scoreboard records 85143 captures, 85137
private retirements, 85307 held-valid checks and 164 buffered-final ownership
checks. These totals include cancellations. Sources remain unchanged.

Eight evidence-auditor tests pass in 1.10 s, rejecting missing/duplicate cases,
short recovery, early publication, missing/short coverage and altered numerics.
A further complete boundary-bench inverse passes in 0.02 s: V1/V2 runtime files
are identical, and the bench only adds the new task/calls, preserving every
previous assertion. Together with the 489-test suite, 498 test cases pass across
these invocations.

## Routed result and next boundary

The unchanged route completes in 50.84 s. Source/checkpoint audits pass and
there are no routing errors. **Setup still fails; do not promote or deploy.**

| Metric | Guard-fact parent | Registered input |
| --- | ---: | ---: |
| WNS (ns) | -1.340 | -1.503 |
| TNS (ns) | -463.636 | -521.325 |
| Failing setup endpoints | 821 | 896 |
| LUTs | 2808 | 2724 |
| Flip-flops | 5691 | 5670 |

New route uses 21 DSPs, 15 RAMB18s and 8319 fully routed nets. Hold +0.058 ns
and pulse +1.830 ns pass with no failures. The diagnostic OOC build still has
114 unconstrained inputs and 124 unconstrained outputs; not board signoff.
Routed DCP:
`35bc4a1bb33ea81220194d7063553eef4b18470ad7fe31555c6eefdd5e0730fd`.

Worst path is now output-bank input-fault Q -> adapter/ledger fault handling ->
destination availability -> registered scheduler engine-metadata CE. It has
seven logic levels and 6.928 ns data delay, including 5.604 ns routing (80.9%).
The final enable net fans out to 72 loads. The new input comparison is no longer
the reported worst path, but overall metrics remain worse than the parent.

Next isolate the private scheduler descriptor capture from its wide capacity/
quarantine enable. In WAIT_BANK the payload can potentially follow selected
metadata privately and freeze on leaving that state. Admission state, phase,
lease, current fault vetoes and registered certificates must remain unchanged.
Prove equality on healthy ownership transfer and demonstrate that any extra
private capture during cancellation cannot start/configure the FFT or publish.
Do not silently apply this change to default callers or weaken availability.
Then actual FFT/fault/reset/service tests and unchanged routing again. This
follow-up is not implemented by the current candidate.

## Evidence retention and remaining release gates

Disk pressure required archiving the completed V1 regression scratch tree,
byte-comparing it, then removing only that unpacked generated tree. Full archive:
`staged-inputidentity-regression-v1-complete.tgz`, 138619522 bytes, SHA256
`578352bbaa058874a3406ae7452d9537defb1d2e47bd5ad4e3cb78ecf2cfbab7`.
It remains in recovery; V1 XML preserves the failed-test explanations in the
curated evidence package. This does not reclassify those two tests as passes.

After actual V2 success, route the complete subsystem under the original clock
constraints and compare WNS/TNS/endpoints, not just synthesis or resource size.
The parent guard-fact route is -1.340 ns WNS / -463.636 ns TNS / 821 endpoints.
The unrelated publication-scope route regressed to -1.888 / -598.888 / 881.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection are
untouched. Full receiver integration, board clocks/CDC/reset, sustained capture,
actual 60 MS/s calibration and Ethernet/IIO remain required before reversible
`.18` canary and `.17` PPU Ethernet-only deployment with pinned rollback.
Final gate: 300-second / 120 ms valid-dwell scanning and blind host GLRT. This
subsystem experiment is neither continuous receiver nor hardware qualification.
