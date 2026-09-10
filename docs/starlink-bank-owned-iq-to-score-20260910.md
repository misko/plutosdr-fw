# Bank-owned coarse IQ-to-score composition: actual-core simulation only

The additive `starlink_pss_iq_to_score_bank_owned.v` passes the six final v3
runners: exact numerical/fault/reset/gap tests at actual 175 and 200 MHz FFT
clocks, plus 64-block continuous canonical15 nominal and bursty-stalled tests
at both clocks. The source, overlap scheduler, energy cache and scorer clock is
100 MHz. Existing receiver defaults and existing RTL modules are unchanged.

This is **not physical timing, receiver fit, CDC signoff, RF or accuracy evidence**.
Parent's diagnostic route of the preceding frozen three-bank slice reported
175 MHz WNS **−2.557 ns** (632 endpoints), through metadata/input guard/result
guard/join acceptance. Its 114/124 missing external delays and other OOC caveats
also preclude qualification. No clock lowering, removed fault fence or receiver
build is authorized by these functional results.

## Composition and ownership

The unchanged overlap scheduler feeds CI16 shifted left two bits into the same
fixed 18-bit BFP 512-point generated XFFT contract. The frozen bank-owned slice
owns forward FFT, unchanged kernel join, exact spectrum multiplication, and
inverse FFT. Actual storage remains three 512×36 banks: source CDC, local private
product, inverse-output CDC. No old forward-result mailbox copy or old transform
FIFO is reintroduced. The 512-entry candidate FIFO is a separate, unchanged
slow-domain buffer for the 447 valid candidates; it is not an extra FFT bank.

The unchanged energy cache sees the original canonical input, independently of
transform progress. The unchanged one-cycle inverse register feeds the existing
512-position qualifier, 65-prefix discard, raw-result FIFO, indexed energy join,
normalization and score lanes. The generated XFFT configuration and rounding,
product arithmetic, both exponents, coefficient energy and score arithmetic are
unchanged. No duplicate scoring implementation or floating-point replacement is
used.

The island still publishes only after its complete private result checks and
the original vendor-event fence. Forward ownership transfers only after the
complete checked product bank becomes available; inverse ACK remains the actual
slow-domain last read. Current/late fault and reset/ACK tests from the frozen
slice study still apply to this unchanged slice, not to a new timing workaround.

Slow output metadata is `{inverse_direction, start[63:0], forward_exp[4:0],
inverse_exp[4:0]}`. The wrapper rejects wrong direction. The downstream unchanged
qualifier independently verifies ordinal, TLAST, constant block identity and both
exponents, including consecutive block starts separated by 447.

Compatibility fault ports need care during later receiver integration:
`forward_fft_fault` is the synchronized aggregate island fault. Kernel/product/
forward-exponent checks remain active inside that aggregate; their individual
legacy compatibility outputs are tied zero in this experimental wrapper.
`inverse_fft_fault` identifies the slow output direction error. Do not interpret
these as the existing production health-category ABI. No fast pulse is sampled
directly as a slow fault cause. Sticky global detector quarantine, explicit
enable/flush recovery, and scheduler gap/index restart remain intact.

## Executed numerical and boundary tests

Each clock runs the immutable original three-block reference four times:
initial healthy replay, fresh replay after an autonomous source-gap restart,
fresh replay after an autonomous source-index restart, and exact replay after
the independent reset/fault tests. There are **5,364 exact scores per clock**;
each epoch also independently checks 1,536 forward, product and inverse words,
their block identity, ordinal, TLAST and appropriate exponent. The original
three full-scale PSS score controls remain 255. Forward/product probes sample
actual acceptance at `fft_clk`; inverse/score probes sample `clk`.

Five slow-output mutations each inject exactly a valid position zero and ONE
malformed beat, then remove valid: ordinal, forward exponent, inverse exponent,
block start, TLAST. The bench requires the immediate specific qualifier sequence
or metadata pulse, then sticky global quarantine. Repeated ordinal errors cannot
mask a missing exponent predicate. Direction is a separate one-beat injection.
Other tests include synchronized aggregate input-guard fault, independent FFT
reset with sticky quarantine, independent slow reset, and source gap/index
discontinuity during an actual forward transform. Gap/index recovery replays
fresh correctly indexed exact data without an intervening enable/flush/reset.
Score READY changes off the acceptance edge; stalled payload remains checked.

## Executed continuous-source capacity tests

Each capacity runner supplies 28,673 contiguous canonical source samples and
requires 64 forward/product/inverse frames (32,768 words each), 28,608 ordered
scores, no leaf/global fault, all 64 progress receipts and bounded retention.
Independent frame/metadata checks run on their actual clock domains. These
deterministic 64-block capacity vectors check order, capacity and liveness, not
FFT/score numerical accuracy; the separate exact replay provides that evidence.

The nominal source uses the exact 15/100 phase accumulator. The bursty source
accumulates arrivals during 12 of every 40 slow clocks, then drains the bounded
backlog on consecutive clocks without gaps or changing the average rate.
The stalled sink blocks 3 of every 97 slow clocks. These are specified test
profiles, not unrestricted stall tolerance or a universal worst-case bound.

| FFT clock / profile | Candidate FIFO max /512 | Energy lookup age max /2048 | Score age max | Forward admission interval, fast clocks |
| --- | ---: | ---: | ---: | ---: |
| 175 / nominal | 356 | 845 | 913 | 5215–5215 |
| 175 / bursty-stalled | 358 | 847 | 914 | 5198–5232 |
| 200 / nominal | 356 | 806 | 874 | 5960–5960 |
| 200 / bursty-stalled | 358 | 808 | 875 | 5940–5980 |

Ages are **canonical source samples**, not accuracy claims. Every run has overlap
queue maximum 1, scheduler ring-retention age maximum 589/2048, and zero forward
input-stall cycles. Nominal admissions are arrival-paced at exactly 29.8 µs,
not measurements of saturated service latency. Bursty admission variation follows
the source delivery pattern; the earlier saturated slice study measures actual
service independently (175 MHz nominal 4540 clocks, tested repeated stalls 4820).

Strict tagged capture-N+1/transform-N and three-epoch capture/transform/score
witnesses are zero in these runs. Their predicate requires transform `RUN_JOB`;
it excludes inverse `ACK_DRAIN`, so zero does not exclude capture/output-drain
overlap. These canonical inputs do not demonstrate three-way active compute
overlap. The preceding saturated slice separately witnessed source-bank overlap.
Capacity acceptance rests on continuous input and exact counts with bounded
queues, not on all stages being busy simultaneously.

## Evidence, automation and limitations

Portable receipts, all 64 progress rows per capacity run, and frozen RTL/bench/
vector/core/log hashes are in `reports/starlink-bank-owned-iq-to-score-20260910.json`.
Full isolated artifacts are under
`hdl/library/starlink_pss_acquisition/build/bank-iq-*-v3/`: each has frozen sources,
generated bench, pre-simulation scope/hash receipt, full project and actual-core
`simulate.log`, and its own top-level Vivado log/journal. All six exited zero and
printed `BANK_IQ_TO_SCORE_ACTUAL_CORE_VERIFIED` only after verification.

Earlier evidence is retained, not upgraded to passes: numeric200-v1 had repeated
malformed-beat masking risk; capacity175-nominal-v1 passed its bench but failed
the empty-terminal-marker automation contract; numeric175/200-v2 checked an
extra registered diagnostic one cycle early and printed explicit FAIL lines.
The original no-message `$fatal(1)` did not stop that simulator run, so final
adaptation supplies a fatal message and final postprocessing rejects explicit
FAIL/FAULT lines even if followed by PASS. Every verifier call requires a
nonempty, unique, exact terminal marker and complete row inventory.

Root independently supplied 43 admission/adaptation/runner-policy tests; 16 new
portable receipt tests and the preceding 19 slice/budget tests also pass: **78
tests**, plus Ruff on the new Python files. The collector rejects missing/extra
frozen files against both the pre-run hash inventory and explicit runtime source
inventory, in addition to altered contents. These unit tests do not add arithmetic
or physical evidence. Handwritten files are additive; the immutable kernel/vector
files and all prior production/default modules are unchanged.

Reproduce with Vivado 2022.2, `general.maxThreads=2`, and new output directories:

```text
simulate_iq_to_score_bank_owned.tcl NEW_OUTPUT numeric FROZEN_VECTOR_DIR 175|200
simulate_iq_to_score_bank_owned.tcl NEW_OUTPUT capacity nominal|bursty-stalled 175|200
python -m tests.starlink_oracle.iq_bank_owned_evidence hdl/library/starlink_pss_acquisition/build --output REPORT.json
```

The new full composition's synthesis resource measurement is the next separate
gate; the existing 1,834-LUT/4,375-FF/21-DSP/7.5-BRAM result is **slice-only**, not
a complete coarse or receiver area budget. No area saving is inferred.

The full objective is unchanged: continuous canonical15 coarse at source15/30/60,
original native samples for sparse fine search, 2.5 MS/s pilot IIO inspection,
.18 before Ethernet .17, and eventually eight targets with 120 ms dwells over
300 seconds. Source-rate adapters, native fine, pilot/IIO, full-receiver fit/
timing/CDC, prolonged control transitions, dwell retunes, and RF accuracy remain
unqualified here. No receiver build, radio, deployment or remote write was made
by this worker.
