# Recorded 25 MS/s PSS test — 9 September 2026

Capture: `cap-20260909T121248-414fb81f488c`.

The existing PSS arithmetic distinguishes a signal-present interval from a
signal-absent interval **when supplied with a GLRT-derived frequency correction**.
The uncorrected PSS run misses the signal-present interval. Independent pilot
GLRT on the same conditioned recording also separates these intervals.

This is targeted offline evidence, not a blind survey, native 25 MS/s FPGA
support, a live receiver test, or proof of precision timing lock. No radio was
accessed or changed.

## What was tested

- Original recording: 25 MS/s, RX0, CH4 upper edge, IF LO 1.9325 GHz.
- Two predeclared, evidence-selected 320 ms windows: 0.50–0.82 s (negative)
  and 36.00–36.32 s (positive). Both, including their filter halos, contain
  observed continuous samples. The recording elsewhere has gaps; those gaps
  are not treated as negative RF observations.
- Downmix by 5 MHz, then explicitly filter/resample by 3/5 to the existing
  15 MS/s canonical PSS input. A centered 481-tap filter has measured passband
  through 6.5 MHz and stopband from 7.5 MHz; this is not preservation of the
  entire original 25 MHz bandwidth. Source timestamps and support are retained.
- Frozen 18-bit Q17, 512-point vendor FFT model, existing coefficient memory,
  overlap-save scoring and existing map gates. No coefficient or threshold
  tuning. Each variant processes 10,739 complete FFT blocks without padded RF
  input and retains 4.8 million scores. Three complete 64-frame maps cover
  256 ms; the remaining 48 frames do not form a complete map.
- Baseline: no residual frequency correction. Assisted: +285,798.946 Hz
  correction, derived from saved positive-window GLRT. The identical correction
  is applied to the negative control. This is external assistance, not blind
  acquisition or calibrated Doppler.
- Separately, the frozen integer pilot path reduces the baseline derivative
  from 15 to 2.5 MS/s. Blind pilot acquisition/GLRT uses fixed 20 ms probes
  at 0, 100 and 200 ms, without PSS timing or frequency seeds.

## Measured results

The existing combined-map gates are peak/median ≥ 1.15 and robust z ≥ 6.

| Interval / PSS mode | Peak/median | Robust z | Passing individual maps | Combined gate |
|---|---:|---:|---:|---|
| Positive, baseline | 1.375 | 4.89 | 0/3 | Fail |
| Positive, assisted | 1.749 | 9.96 | 3/3 | Pass |
| Negative, baseline | 1.360 | 5.09 | 0/3 | Fail |
| Negative, assisted | 1.345 | 4.83 | 0/3 | Fail |

All four frame-scrambled combined-map controls fail. Scrambling is an algorithmic
control, not another independent RF recording. No conditioner, derotation, pilot
or FFT arithmetic overflow/clipping was reported.

Blind pilot GLRT margins are 0.449, 0.464 and 0.380 in the positive interval,
versus 0.00675, 0.00516 and 0.00643 in the negative interval. The legacy 0.025
margin gate separates all six probes; it is not a calibrated false-alarm bound.
Saved original-rate GLRT similarly passes 31/31 overlapping positive windows
and 0/31 negative windows. These overlapping windows are not independent trials.

### Timing interpretation

Assisted PSS individual-map maxima occur at 400.467, 398.067 and 398.267 µs
modulo the nominal 750 Hz frame period. Independent pilot estimates are
399.267, 399.667 and 400.067 µs at their three probe times. Saved original-rate
GLRT has a median phase of 399.720 µs across the positive 320 ms interval.
These are nearby coarse phases, not measurements of absolute timing error.
Exact support-matched comparisons must account for whole FFT block dependencies,
the resampling filter, and the pilot filter's 269-canonical-sample group delay.

The completed support join gives PSS-minus-saved-GLRT median differences of
+1.013, −1.573 and −1.560 µs for the three maps. Strictly included pilot probes
give −1.6 and −1.8 µs in maps 1 and 2. The first pilot probe is retained but
excluded from that strict timing comparison because its filter history extends
before the first PSS FFT block. These are estimator disagreements, not an
absolute timing-error bound. See `starlink-capture25-comparison-20260909.json`.

The combined PSS search chooses +9.375 ppm, the edge of its tested drift bank.
That is an unresolved boundary optimum, not an established clock-rate estimate.
Individual maxima also move between nearby lobes. Fine PSS refinement and a
qualified stable track have not been run on these windows. Neither a 15 MS/s
canonical grid nor a 2.5 MS/s pilot estimate proves ≤16.7 ns absolute accuracy.
The independent map audit finds multiple nearby correlation lobes and only a
2.5% score advantage for the boundary hypothesis over +3.125 ppm. The frozen
template has substantial ±8-sample autocorrelation sidelobes. This motivates
explicit ambiguity/refinement tests, not relabeling the current winner as lock.

Pilot frequency estimates retain alias ambiguity: the final positive probe
reports about +512.6 kHz, while the earlier probes report about +286 kHz.
The saved original-rate GLRT also contains a higher alias branch. No alternate
branch was silently removed or used to retune the completed experiment.

## Interpretation and next tests

1. Keep pilot acquisition as an independent frequency/timing cross-check.
   This recording supports using qualified pilot CFO to assist PSS; it does not
   establish that unassisted PSS covers the LNB's frequency uncertainty.
2. Next use a separate earlier pilot probe to choose CFO, then test disjoint
   PSS intervals in other continuous observed segments. Retain all negatives
   and frequency aliases. The present same-window assisted result is not a
   held-out performance estimate.
3. Investigate the drift-bank boundary and nearby PSS lobes, then exercise the
   fine timing stage with known timing before claiming lock or sample accuracy.
4. Resolve the discovered cross-layer half-subcarrier frequency-plan discrepancy
   before live hopping. This replay uses the deployed Leo and existing live-PSS
   convention (+5 MHz translation), not the newer midpoint-only scanner planner.
5. Keep physical FPGA timing closure, paired IIO transport, .18 canary testing,
   and .17 outdoor deployment as separate unfinished gates. This offline test
   changes none of their qualification states.

## Evidence

- `cap25-reference-20260909.json`: immutable saved-analysis extraction and
  source/epoch/frequency conventions.
- `starlink-capture25-{positive,negative}-replay-20260909.json`: full replay
  receipts, original compressed/uncompressed chunk hashes, conditioner/kernel
  identities, all maps, controls, source supports and frozen-source hashes.
- `starlink-capture25-{positive,negative}-pilot-20260909.json`: all pilot
  candidates, actual imported numerical-backend identities and no-PSS-seed policy.
- `starlink-capture25-comparison-20260909.json`: exact support joins, all
  qualified estimator differences and explicit exclusions.
- `starlink-capture25-map-audit-20260909.json`: all original drift hypotheses,
  correlation-lobe ambiguity and unchanged-run interpretation.
- `starlink-capture25-rtl-20260909.json`: actual numerical simulation results,
  fixture/RTL hashes and retained failed/superseded attempts.
- Numerical arrays and frozen source copies remain under
  `hdl/library/starlink_pss_acquisition/build/capture25-{positive,negative}-v1`.

## Actual recorded-data RTL check

Both baseline and assisted snippets pass the actual realtime FPGA FFT/score
simulation, not just the C model. Each contains 1406 recorded canonical samples
starting at index 540005364 (full-replay block 12). The fixture verifies exact
identity of all input samples and all 1341 scores with their full-window slices.
The bench checks all 1536 forward, product and inverse values, exponents and
metadata, all score values/timestamps, real output stalls and fault/reset
quarantine. Both runs observe 154 stalled cycles and FIFO high water 358.

The initial attempt failed before elaboration because Vivado generated broken
shell quoting for an HDL-literal generic. The runner now passes an exact decimal
origin and verifies its full-width hexadecimal value in the bench. A second
numerical run passed but retained one stale policy text assertion; the final
v3 runs repeat successfully with the corrected policy snapshot. All attempts
are retained; no runtime RTL, coefficient, threshold or clock was changed.

These three-block tests do not execute complete phase maps, the fine detector,
DMA/IIO, sustained hardware capture or physical timing. Those remain separate
qualification gates.

## Software verification and branch scope

The root rerun passes 316 focused conditioner, admission, pilot, fixture,
comparison and runner-policy tests. Ruff and diff checks pass. Recomputing the
comparison from its five tracked input receipts produces byte-identical JSON.
Experimental firmware/test work remains on
`codex/starlink-rx-only-do-not-merge`; no firmware changes are merged into main.
PPU and all radios are unchanged by this recording test.
The recorded-data HDL test runner/bench are committed and remotely verified at
`1003cf0f84ef9c6661ff05483c992133ba6bc059`; their detector runtime remains
unchanged from `deb9badcc9a521d4694ceebe0223c97344cb7566`.
