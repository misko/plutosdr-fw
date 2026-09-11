# Clocked inverse-final validation — DO NOT MERGE

Reference: private-capture FW `fcc3dc202`, HDL `c25126a2e`, actual FFT/382 tests
passed, routed WNS -1.969 ns. Its worst path still ran through global metadata/
fault qualification into completion-pending, followed by inverse awaiting-ACK.

## Implementation and authorization contract

The result guard gains default-off `STAGED_PRIVATE_FINAL`, enabled only for the
inverse owner in the experimental FFT/buffer integration. Forward behavior and
the guard's legacy `mailbox_input_valid`/`mailbox_commit_valid` predicates remain.
Default callers retain immediate final consumption. The opt-in inverse producer
instead closes on a clocked **private** certificate, not legacy same-edge public
permission. Its `commit_pulse` and active/awaiting-ACK transition follow that
private consumption; they do not prove publication to the reader.

The request requires an owned held final word, completed-input certification,
both 512-word counts, frame/status/exponent observations and the final fence.
Only then does a seven-bit certificate snapshot the remaining independent veto
facts: completed-input/external fault, mailbox fault, output reservation, frame,
status, raw output and watchdog. A late first legal status can arrive before
the request; it cannot freeze an incomplete certificate. The existing one-shot
certificate primitive supplies held evidence, no refresh, single consumption
and reset/quarantine cancellation. Descriptor and final word remain owned.

The inverse guard and mailbox controller consume the same private handshake.
The descriptor becomes locked/pending and is checked on the next edge. A new
fault on consumption may allow this private state transition, but the original
current-fault bank-authorization predicate still vetoes actual publication.
Registered fault/epoch abort cancels before replay/notification/reuse; actual
bank request transition and final-reader ACK remain required. This changes the
meaning of the experimental `output_complete_accept`: it is now private close,
not the old same-edge fault-qualified completion. No public veto was replaced.

## Test development and retained failed attempts

V1 failed the numerical scoreboard at the added final-hold cycle: the previous
monitor counted every private write as a new sample. The explicit-commit bank
permits an identical held-final rewrite. V2 checks that rewrite against the exact
prior word and full descriptor, requires it on the certificate consumption edge,
and counts it separately. Each healthy inverse block must have exactly one:
18 total, with the unchanged 64,512 unique numerical-record inventory.

V2 passed six numerical contexts and final cases 0–6, but timed out in the
stalled-completion test. After releasing forced READY, the falling-edge polling
loop could miss a one-cycle acceptance already consumed at the rising edge.
V3 observes that actual handshake edge, with an explicit 32-clock resume bound.
The absolute 3 ms simulation deadline is not increased. Runtime RTL is unchanged
between V1/V2/V3; only bench/helper evidence handling changes. Both earlier
attempts retain failed outcomes and are not eligible for routing.

## Verification requirements and observed preflight

The entire prior numerical, stopped-reader reset, fault, admission, producer
completion, replay, writer and private-capture campaign is retained. The private
capture fault-edge case now requires observed private close/lock/pending, while
still rejecting all actual publication, reads and release after that fault.

Eight new final-validation cases cover: vendor fault before snapshot; vendor
fault at consumption; either reset before snapshot; extra raw output or duplicate
status at consumption; a late first legal status; and 16 clocks of completion
backpressure followed by real reader completion. The two healthy cases require
512 correct reads/one release each. All six cancellation cases require no
publication/reuse/read/release. A per-edge assertion compares the offered seven
checks with the complete legacy final predicate, and accepted private closes
must have a captured permit. The original current bank authorization is checked
throughout the full test.

Preflight passes two tests. Certificate unit tests now include width seven:
every individual zero/X/Z bit rejects, evidence holds, no refresh or double
consume, quarantine/reset cancel, and a fresh epoch recovers. Four unsafe
certificate mutations fail for each of widths 7/22/28. Together with the prior
private-capture block comparison, **21 unit tests pass in 0.17 seconds**.

V3 actual generated-FFT verification passes in **128.73 seconds**, including
all eight new cases and every prior campaign. All **64,512 numerical records**
independently match the pinned reference. Sorting the complete CSVs also proves
the same record multiset as the private-capture baseline: the raw CSV bytes
differ only because stream interleaving changes with the added clock.

Service intervals are 3660/3660/4929/11728/3660/3660, versus the private-capture
baseline 3659/3659/4927/11727/3659/3659. The unchanged 5215-cycle cap passes for
the five qualifying contexts; the intentionally 9000-clock-stalled reader
retains no real-time service claim. There are exactly 18 healthy final rewrites,
32,634 private descriptor loads, 74,848 holds and 18 accepted captures. Full
timestamp contexts pass; both stopped-reader resets purge in five slow edges
and return a fresh 512-word result. Total receipts including aborted jobs are
114 admissions and 83 completions. Source-matched V3 synthesis passes in
**99.11 seconds**. Before/after source checks pass.

**397 regression tests pass in 51.78 seconds**, including ten final-evidence
parser controls. V3 route completes in **51.67 seconds** and its independent
source/checkpoint/report audit passes. The measured timing, however, regresses:

| Version | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | -1.969 ns | -813.676 ns | 914 |
| Clocked inverse-final validation | **-2.379 ns** | **-941.022 ns** | **1038** |

Timing remains FAIL at 1038 / 13803 endpoints; this candidate is not a timing
improvement and is not promoted. Hold +0.064 ns and pulse +1.830 ns pass. All
8335 nets route with zero errors. Resources: 2738 LUT / 5669 FF / 21 DSP /
15 RAMB18. Five critical CDC findings, 208 warnings and 114/124 unconstrained
I/O remain. Device, actual generated FFT, diagnostic 100/175 MHz clocks and
route recipe are unchanged. No timing waiver or full-receiver claim.

The worst path is now product-bank held metadata → metadata comparison →
shared completion/input fault checks → forward acceptance → kernel ROM's
`expected_bin_index_reg[5]/CE`. It has 11 levels and 7.804 ns data delay,
including 5.922 ns routing. Completion-pending is no longer the worst endpoint;
this does not prove that every completion/ACK path is timing-clean.

Next inspect the forward/kernel ordinal-control contract. Private payload loads
already avoid global acceptance gating, but expected-index state still uses it.
Any independent private advance must retain the public per-bin identity check,
freeze under real backpressure, preserve block boundaries, and be quarantined
before publication on fault/reset. Compare both the better private-capture
reference and this staged-final variant; do not assume that composing changes
will improve routing. Require actual FFT equivalence/cancellation and another
source-matched route before receiver integration or additional features.

V3 inventory: `8df8afa4b1d98bea85d33432eb8d34750a772e003dd89d619d1286591bbb0a97`.
V3 CSV: `30d99ca45c77ab72bae3a982b4097fded1dd04e8b03995e742c401020c9c9c96`.
V3 synthesis DCP: `b667cc03ce83f56e67357e3b198a48f949deb5c8357c55d4d5599b472286bf24`.
V3 routed DCP: `d860b58833cae1af963e04f5183fb98fe102e7d62fcd12cbc31c6bdc3aa0a67d`.

## Unchanged full release gates

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver route/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration precede `.18` reversible canary, then
`.17` PPU Ethernet deployment with pinned rollback. Final verification remains
the 300-second, 120 ms valid-dwell scan and blind host GLRT comparison. No radio,
PPU, main branch or primary production HDL gitlink is changed by this experiment.
