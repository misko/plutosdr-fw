# Narrow pilot coarse acquisition and causal frequency assistance

This completed offline experiment supports studying pilot timing as a candidate
source and retaining prior-only frequency assistance. It does **not** select a
replacement for canonical 15 MS/s coarse PSS. Narrow filtering discards much of
the PSS evidence, and the real pilot estimates retain material CFO aliases even
after an earlier correction improves their scores. Both FPGA stages, the
2.5 MS/s IIO product, and the original 15/30/60 MS/s scanner requirements remain.

No radio, PPU, deployment, HDL implementation, full receiver build, remote push,
or merge was performed. Work is confined to the independent `narrow-coarse`
firmware worktree; its HDL worktree remains at
`eb96c64738697c10b9c0abb379ab64f6a4a5c59c`.

## Predeclared experiment and evidence

The executable runner is `tools/starlink_narrow_coarse_study.py`; its bounded
support/latency tests are `tests/test_starlink_narrow_coarse_study.py`.
The immutable plan, individual case receipts and combined result are in
`reports/narrow-coarse-20260910-v1/`. The plan was written before any acquisition
or held-out evaluation. It pins the actual local oracle sources, historical
prior receipts, PSS reports and SHA256 of every input probe.

- Six supported positive cases must have GLRT margin >0.15, epoch error <3
  output samples, CFO error <1000 Hz, and no arithmetic saturation.
- Two noise controls must have margin <0.025. Four cases outside full nominal
  carrier support are diagnostic, with no positive/miss acceptance label.
- Real candidate margin is >0.025. Earlier activity labels and GLRT candidates
  are explicitly not independent RF truth; no false-alarm-rate claim follows.
- Unknown or incomplete frequency support is retained. Timing/CFO from later
  PSS never seeds GLRT. Earlier blind pilot evidence supplies only the declared
  pre-filter frequency correction.
- A 120 ms candidate budget includes observation, pilot group delay and measured
  search computation. Transport and command times remain unmeasured, so this
  study cannot qualify online handoff.

Run with the read-only Leo Python 3.13 environment:

```sh
/home/mouse9911/gits/leo-tracker-reduxredux-all-rate-main/.venv/bin/python \
  tools/starlink_narrow_coarse_study.py plan \
  --evidence-root /home/mouse9911/gits/plutosdr-fw-starlink-rx-only \
  --leo-root /home/mouse9911/gits/leo-tracker-reduxredux-all-rate-main \
  --output reports/NEW-UNUSED-STUDY
/home/mouse9911/gits/leo-tracker-reduxredux-all-rate-main/.venv/bin/python \
  tools/starlink_narrow_coarse_study.py run \
  --plan reports/NEW-UNUSED-STUDY/plan.json
```

Existing report paths are never overwritten. Per-case receipts survive an
interruption. A successful process exit means the study executed; inspect
`all_predeclared_observable_fixtures_pass` for fixture acceptance.

Plan SHA256:
`cf701ae2ad5c11434469869d2a52b9075ca5a4432211cb6f3b64cbd1d393af66`.
Result SHA256:
`cd2a63e676c7ec02ec2d30540f3337cd02498745aa3cbb6ae37093d0c756f16e`.
All artifacts total 525,938 bytes. No IQ recordings were created. Each real
probe reads only 301,200 canonical complex samples, 1,204,800 bytes including
600-sample halos on each side, from an existing conditioned derivative. The
full derivative is not reread or newly revalidated against original ADC IQ.

## Actual filtering and observability

The current coarse PSS input is **15 MS/s**, not 2.5 MS/s. The separate pilot
branch mixes the frozen upper/lower centers (+2.8125/-3.046875 MHz), applies the
existing Q17 31-tap /2 and 255-tap /3 filters, and emits CI16 at 2.5 MS/s.
The experiment uses that fixed-point oracle, including its rounding, clipping,
absolute phase and support flags. Additional frequency correction here is an
offline complex rotation followed by CI16 rounding before that fixed pilot DDC;
it is not an implemented FPGA NCO or a qualified RF retune.

The passband edge is 1.1 MHz and stopband begins at 1.25 MHz. Group delay is
269 canonical samples =17.933 us, and history invalidity after reset lasts
538 samples =35.867 us. Its output counter names the newest input; subtract
269 to obtain the canonical signal-center coordinate.

The eight published pilot carrier centers span +/-820,312.5 Hz. All centers
therefore remain inside the declared passband only for residual CFO
|f|<=279,687.5 Hz. Including one useful-symbol first-null spacing would reduce
that illustrative bound to 45,312.5 Hz. OFDM symbol transitions have spectral
tails, so neither calculation proves preservation of a strictly band-limited
pilot waveform.

The prior +285,941.794 Hz is an **uncorrected frequency estimate**. It is slightly
outside the all-carrier-center bound only before applying it. Applying that
correction moves a signal on that hypothesis to approximately zero residual.
The real residual is estimated independently below and remains alias-ambiguous.
At uncorrected +1.2 MHz, four carrier centers are in the filter stopband; a
2.5 MS/s product cannot promise the complete pilot band over arbitrary +/-1.2 MHz.

For the frozen 66-sample PSS templates at zero residual, the linear frozen-FIR
spectrum calculation retains 20.98% lower/21.46% upper PSS energy, -6.78/-6.68 dB
relative to the canonical template. With uncorrected +285.942 kHz these become
16.38%/11.73%, -7.86/-9.31 dB. These are energy measurements, not measured detector
SNR loss or a new numerical contract. The illustrative centered-frequency
second-moment metric over the ideal +/-1.1 MHz band retains only 0.51%/0.66%
of the zero-residual canonical PSS timing metric. It excludes multipath, colored
noise, channel/CFO nuisance parameters and finite-SNR estimation error. It
supports preserving original-rate fine samples, not an absolute accuracy claim.

## Known signal and noise results

Twelve 20 ms pilot/PSS/noise fixtures ran on both edges, using the published
pilot frame, frozen canonical PSS and one fixed noise seed. All six supported
positives and both noise controls passed their predeclared gates with zero
source, correction or DDC saturations. Supported positive margins were
0.875–0.908 and maximum absolute CFO error was 1.74 Hz. The generated epoch was
aligned to the exported sample lattice; its zero observed timing error is not
a test of arbitrary sub-sample timing, weak signals or multipath.

At +400 kHz uncorrected, margins remained 0.880/0.893 despite incomplete nominal
passband support; these were retained as diagnostic observations. At +1.2 MHz,
the lower case produced margin 0.03265 at an incorrect epoch/CFO and the upper
case margin 0.01873. They remain `unobservable_full_pilot_contract`, not misses,
false alarms, or qualified candidates. With a **known-truth** +1.2 MHz pre-filter
correction, both became supported and passed. That last pair demonstrates what
centering preserves; it does not demonstrate how to acquire the correction.

## Held-out comparison and unresolved aliases

Three blind 20 ms probes from the earlier 36.00/36.10/36.20 s pilot observation
were repeated to measure runtime and verify the prior evidence. They reproduce
the approximately +286.139/+285.744/+512.585 kHz estimates. The frozen policy
selects the first two as its sole supported <=10 kHz cluster and retains the
third as an unresolved minority alias. No later result changes that choice.

The new tests use the first fixed 20 ms of each pre-existing later 320 ms
episode. The PSS figures below are the already retained combined **256 ms**
three-map results within those episodes; their exposure is longer than the new
20 ms pilot probes. This comparison does not claim equal integration or RF truth.

| Later probe start | Existing 15 MS/s PSS z, baseline / prior-assisted | New 2.5 MS/s GLRT margin, uncorrected / prior-corrected | Pilot phase, modulo frame |
| --- | --- | --- | --- |
| 1.00 s | 4.9699 fail / prior abstained | 0.01354 / prior abstained | No admitted candidate |
| 1.50 s | 5.1829 fail / prior abstained | 0.00637 / prior abstained | No admitted candidate |
| 36.50 s | 4.9809 fail / 8.4744 pass | 0.54913 / 0.66082 | 400.4667 us in both variants |
| 37.00 s | 4.7214 fail / 8.0766 pass | 0.47183 / 0.62049 | 401.2667 us in both variants |

The two negative pilot results are `no_candidate_coverage_unknown`, preserving
the absent calibration/observability evidence. They are not confirmed RF absence.
Neither successful pilot score nor the historical coarse PSS score is fine timing
truth. The original 25->15 conditioning itself preserves only its declared
<=6.5 MHz passband and does not qualify native 25 MS/s or 30/60 MS/s hardware.

Frequency selection remains problematic:

| Probe | Applied correction | Best remaining CFO | Reconstructed uncorrected estimate |
| --- | --- | --- | --- |
| 36.50 s, uncorrected | 0 | +511,564 Hz | +511,564 Hz |
| 36.50 s, corrected | +285,942 Hz | +225,789 Hz | +511,731 Hz |
| 37.00 s, uncorrected | 0 | +282,647 Hz | +282,647 Hz |
| 37.00 s, corrected | +285,942 Hz | +223,888 Hz | +509,830 Hz |

The first corrected probe also retains -1,976 Hz (margin 0.0760) and +453,207 Hz
(margin 0.3276), at the same epoch as its best candidate. The second retains
+451,392 Hz (margin 0.2810). Separations are near the 227.273 kHz reciprocal
symbol duration. The configured acquisition domain is +/-400 kHz; subsequent
GLRT refinement can report estimates beyond that domain. Final CFO bounds must
therefore be validated separately. A single best-score CFO is unsafe as an
automatic narrow fine-search seed. Preserve aliases or abstain until independent
frequency evidence resolves them; a high GLRT score alone does not resolve them.

## Causal deadline and original 60 MS/s fine-search budget

The measured machine is `gauss`, Intel Core Ultra 9 285K, x86_64 Linux, Python
3.13.15, NumPy 2.4.6, using the recorded Leo native acquisition extension. Its
path and binary hash are in `study-result.json`. These are individual wall-clock
measurements, not repeated capacity benchmarks, ARM timings or target throughput.
Total study execution was 2.853 s.

Real blind acquisition plus GLRT took 28.13–62.16 ms per 20 ms input. The separate
Python fixed-DDC model took 57.82–71.72 ms; those model costs are not charged to
an architecture where the already-existing FPGA exports the pilot stream. They
must be charged if this complete software conditioning path is proposed instead.

The repeated prior searches sum to 105.49 ms. The conservative historical prior
full original-input envelope ends at 36.3202 s. The new held-out canonical
input halos begin at 36.49996/36.99996 s, leaving gaps of 179.76/679.76 ms.
The earlier centered 25->15 resampler requires another 80 original25 samples
(3.2 us) of support: actual original-input lower bounds are
36.4999568/36.9999568 s, giving conservative gaps of 179.7568/679.7568 ms.
Ignoring all transport/command costs, a batch starting after that prior envelope
has 74.269/574.269 ms of remaining slack on this host. This is a measured necessary
budget check; it is not proof that a live command was applied before the input.
The original prior policy's three probes extend through 220 ms of source time,
and its retained full envelope is 320.4 ms. That prior policy cannot fit inside
a 120 ms visit. A prior from an earlier same-target visit needs explicit age,
alias, tuning-reference and drift validation.

For a single new 20 ms pilot observation, the measured host-search range gives
48.14–82.17 ms from visit start to a candidate, assuming an FPGA pilot filter and
zero transport/command latency. Waiting up to one next 750 Hz frame gives
49.48–83.51 ms before that future frame; the fine computation and its result
drain remain additional. Appending a 64-frame PSS map instead reaches
133.48–167.51 ms and cannot fit the visit. Three existing maps still require
256 ms even with no assistance. A shorter lock rule requires a separately
qualified sensitivity/false-alarm policy.

Retrospectively refining the **same earlier input** at original 60 MS/s would
require a full-rate CI16 ring of 11,554,588–19,721,804 bytes for these optimistic
candidate times, before transport and fine latency. A whole 120 ms is 28.8 MB
at 240 MB/s. That does not fit the device's 60 BRAM tiles (276,480 raw bytes,
only 1.152 ms even if all were available), and the complete receiver already
uses most BRAM. This experiment does not introduce full-rate DMA. Scheduling a
future PSS avoids that long retrospective buffer but requires valid frame-period
prediction and a live handoff interface.

For source60, one pilot sample is 24 original samples and a canonical center
maps to four original samples; existing source conditioners already provide
center-coordinate indexes. Correct the pilot delay exactly once. The current
fine tracker has 264 taps and 241 qualified lags over +/-2 us (120 original
samples on each side), with 257 raw guard lags. Its minimum command lead is
256 original samples =4.267 us; actual transport/CDC lead needs extra margin.
It schedules future samples and does not supply retrospective history or a
runtime CFO compensator.

The synthetic acceptance bound of three pilot samples would correspond to
1.2 us/72 original60 samples, leaving only 0.8 us inside that fine aperture.
An unqualified 10 ppm period error accumulates 0.8 us after 80 ms, consuming
that remainder. A nominal 0.968 s eight-target revisit accumulates 9.68 us at
10 ppm and exceeds the aperture. These are error-budget examples, not measured
clock drift. The observed pilot/PSS phases use different integration supports;
they do not establish a guaranteed live fine-search radius. Full-rate sample
spacing of 16.7 ns is not measured timing accuracy.

## Remaining decision gates and validation

The proposal needs a local visit-tagged handoff carrying source-counter support,
coefficient/frequency identities, applied correction and residual alias list,
period estimate/age, uncertainty, accepted command deadline and result/fault
receipts. The current fine tracker needs an explicit way to test or compensate
multiple CFO hypotheses. No control interface or target compute capacity is
implemented by this experiment.

Admission must charge the measured return/control path and retain enough of the
same valid visit for the complete fine input and result contract. A late result,
expired prior, exhausted visit, or changed visit/edge must reject the request.
An unresolved CFO identity must either abstain or explicitly schedule the
retained hypotheses; it must not silently choose whichever alias scored best.

Unresolved qualification includes weak-signal and false-alarm sweeps over many
independent seeds, all timing phases, clipping/interference/multipath, modulated
filter sensitivity, long-term alias selection, period drift, equal-support
PSS/GLRT comparison, source60 known-origin fine replay, and actual end-to-end
transport/command latency. Preserve negatives and unobservable visits in all
such tests. Blind GLRT remains free of FPGA timing/frequency seeds. Architecture
promotion still needs both PSS stages and the full-image/.18-before-.17 live gates.

Executed validation: the new nine tests plus existing causal-prior and pilot-DDC
tests all pass, **69 passed**. Ruff passes on both new Python files. The study
completed all twelve synthetic and nine real probes, with all predeclared
observable fixture gates passing. HDL files and production behavior are unchanged.
