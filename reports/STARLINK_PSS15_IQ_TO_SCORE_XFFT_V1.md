# Starlink PSS 15 MS/s generated-XFFT IQ-to-score checkpoint v1

Status: **PASS OFFLINE / DO NOT MERGE / NOT ROUTED / RADIO UNTOUCHED**

This checkpoint closes the source-only 15 MS/s path from continuous CI16
accepted samples to exact normalized PSS timing scores. It does not connect the
score stream to the phase map, integrate the detector into the RX shell, prove
placement and routing, build firmware, or qualify a radio.

## Implemented datapath

`starlink_pss_iq_to_score.v` composes the previously qualified blocks into one
continuous path:

1. The non-backpressured CI16 stream feeds both the 512-sample overlap-save
   scheduler and the exact 66-sample energy cache.
2. Scheduler samples are converted exactly from Q1.15 to Q1.23 by an eight-bit
   left shift and enter the forward generated XFFT.
3. The strict adapter validates configuration, 512-beat framing, natural-order
   indexes, TLAST, status, exponent, and absolute block identity.
4. A new one-entry join captures every accepted forward complex bin beside the
   synchronous, hash-locked upper-edge PSS kernel lookup.
5. The Q1.23 complex product enters a second generated XFFT configured for the
   inverse transform. The forward and inverse block exponents remain separately
   associated with the block.
6. The candidate tail discards overlap-save indexes 0 through 64, joins each of
   the remaining 447 correlations to its exact energy window, and emits one
   exact eight-bit normalized score for each absolute candidate start.

Every constituent malformed transaction is suppressed locally. The top-level
detector quarantine is registered and clears all retained transactions through
the common pipeline reset on the next clock. This keeps same-cycle local
fail-closed behavior without creating a combinational fault/backpressure path
through the complete detector.

## Deterministic generated-core replay

`tools/generate_starlink_pss15_pipeline_vectors.py` builds a deterministic
1,406-sample CI16 stream with exact upper-edge PSS controls at relative starts
100, 447, and 1,000. It uses the installed Vivado 2022.2 XFFT v9.1 bit-accurate
C model in a self-cleaning temporary directory; no proprietary model files are
retained in the repository or vector output.

The source-only top is then simulated with two actual regenerated XFFT v9.1
behavioral instances using the frozen 512-point, signed 24-bit,
block-floating, convergent-rounding, natural-order, radix-4-burst definition.
At a 100 MHz acquisition clock and exact 15 MS/s input cadence the test checks:

| Boundary | Exact transactions |
|---|---:|
| CI16 samples | 1,406 |
| Forward-XFFT bins | 1,536 |
| Kernel-product bins | 1,536 |
| Inverse-XFFT bins | 1,536 |
| Normalized timing scores | 1,341 |

All values, indexes, block starts, TLAST values, and forward/inverse exponents
match the independent model. All three inserted PSS controls score 255, 1,071
scores are nonzero, output backpressure is exercised, and the maximum observed
candidate FIFO occupancy is 345 of 512. After the good replay, a forced
adapter quarantine proves registered global fault propagation, score
suppression, and disable/re-enable recovery.

The frozen vector evidence is
`reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json`, SHA-256
`6eaf98f478b1222042aca89e76828984f6bde6e486f0eacc06b5067f3b5d296d`.
The concise simulation summary is
`reports/starlink-pss15-iq-to-score-xfft-simulation-summary.txt`, SHA-256
`cb2526ba5b1fc464150df1801a6cdd7fb8280fa56b53264a1039d277293ec754`.

## Full-composition synthesis gate

The initial whole-path OOC synthesis exposed a 19-level global
fault/ready/fault path with setup WNS `-3.933 ns` and 385 methodology timing
warnings. Registering the global fault quarantine reduced that to `-1.888 ns`
and nine warnings. Removing global control from internal ready propagation,
while preserving each block's local same-cycle suppression, produced the final
passing result.

Vivado 2022.2 regenerated the same XFFT IP, linked both instances, and ran
post-synthesis optimization for `xc7z010clg400-1` at 100 MHz:

| Resource/check | Result | Device use |
|---|---:|---:|
| LUT | 7,340 | 41.7% |
| Registers | 11,362 | 32.3% |
| RAMB36E1 / RAMB18E1 | 6 / 25 | 18.5 tiles, 30.8% |
| DSP48E1 | 32 | 40.0% |
| Setup WNS | +0.099 ns | pass |
| Hold WHS | +0.011 ns | pass |
| Methodology violations | 0 | pass |
| Nonzero `check_timing` categories | 0 | pass |

The frozen OOC summary is
`reports/starlink-pss15-iq-to-score-xfft-ooc-summary.txt`, SHA-256
`c958aa316e0cf3177f8134c3c885a6e54d4dee4a25837120d1eb6e084d2c8c24`.
This is an unplaced OOC result. Its positive margins are narrow and do not
replace a complete-shell route.

The separately qualified phase map uses 542 LUTs, 722 registers, and 20
RAMB36E1 tiles. An additive planning view is therefore 7,882 LUTs, 12,084
registers, 38.5 BRAM tiles, and 32 DSP48E1s: 44.8%, 34.3%, 64.2%, and 40.0% of
the Zynq-7010. That is encouraging headroom, not a composed utilization or
routing claim.

## Source boundary and next gate

The HDL source is locked at commit
`c6b55bd5e9afb2da293b2b08fb36cc0609586868`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-iq-to-score-xfft-v1` on the
experimental `codex/starlink-rx-only-do-not-merge` branch. Firmware-main guard
PR #92 passed all five required checks and merged as
`eb0fe23673e5318b42dbe9bf3e972cb9a0be217c`; it protects this exact gitlink
before the experimental parent advances.

No IIO context, USB device, network radio, serial console, DFU endpoint, or
flash was opened. The only reserved future qualification target remains serial
`104000bac4950008230026001b440a003a`; every other local radio remains free.

The next 15 MS/s gate is to connect the exact score/index stream to the frozen
20,000-phase, 64-frame map, add control/telemetry and RX tap boundaries, then
place and route the complete one-RX shell. Only after deterministic shell
replay and RAM-only exact-radio qualification should the rate ladder introduce
the 30 MS/s x2 front-end, followed later by 60 MS/s x4.
