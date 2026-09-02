# Starlink PSS15 composed candidate-score path checkpoint

Status: **experimental source-only RTL; do not merge, build into a radio image,
release, or persistently flash**.

This checkpoint completes the logic from a correctly scaled 512-point IFFT
output stream and an independently populated sample-energy cache to an ordered
eight-bit normalized score stream. It does not instantiate either XFFT core,
package the coefficient ROM, connect the overlap scheduler or phase map,
integrate the RX-only shell, or claim raw-IQ-to-score equivalence, PSS timing,
frame alignment, SSS, or over-the-air detection.

## Composed contract

`starlink_pss_ifft_qualifier.v` consumes the complete IFFT stream. It validates
indexes 0 through 511, TLAST at index 511 only, stable forward/inverse block
exponents and block start, and a 447-sample start increment between consecutive
overlap-save blocks. Indexes 0 through 64 are discarded. Indexes 65 through
511 become the 447 candidate starts `block_start + ifft_index - 65`. Any
sequence or metadata error latches a fault and prevents malformed output until
flush.

The existing 512-entry raw-result FIFO absorbs the dense 447-result burst.
`starlink_pss_energy_join.v` drains one raw item into the absolute-indexed
energy cache and retains its correlation/exponent metadata until the response.
It may retire a response and issue the next request on the same clock. A cache
miss, response-index mismatch, or orphan response is consumed but never
emitted; it latches a quarantine fault rather than manufacturing a zero score.

`starlink_pss_score_prepare.v` forms the exact 69-bit numerator/denominator,
and `starlink_pss_score_lanes.v` alternates accepted ratios across two identical
eight-iteration dividers. A separate output-lane phase advances only when the
selected score is accepted, preserving input order through arbitrary output
stalls. The default coefficient energy is the frozen upper-edge value
`1073742825`. The lower-edge value `1073776498` remains representable but is
not qualified by this default-parameter checkpoint.

`starlink_pss_candidate_score_path.v` composes those units and latches
qualifier, FIFO-capacity, and cache-join fault causes. A fault immediately gates
the external IFFT and score interfaces. It intentionally does not distribute a
same-cycle combinational flush through every ready chain: the acquisition
controller must observe the sticky fault and explicitly apply the common flush
to this path and its external energy cache. That action clears all in-flight
state synchronously and is the only recovery path.

## Deterministic simulation

Five new self-checking tests cover the composition:

- two complete IFFT blocks (1,024 inputs) produce exactly 894 ordered
  candidates while 130 invalid-prefix results are discarded; deterministic
  stalls plus index, TLAST, exponent, and next-block-start faults are checked;
- 1,000 consecutive energy joins sustain one lookup per clock, preserve all
  metadata, and separately quarantine miss, mismatch, and orphan responses;
- 1,500 ratios exercise both divider lanes, exact order, zero denominators,
  input/output stalls, and deterministic post-flush lane phase;
- 4,112 signed correlation/energy/exponent vectors are converted through ratio
  preparation and both divider lanes and compared to an independent Python
  arbitrary-precision `round_ties_even(255*N/D)` oracle; and
- a real `starlink_pss_energy_cache` is populated from 512 consecutive CI16
  samples, then a dense 512-result synthetic IFFT block enters without
  backpressure. All 447 candidate identities and final scores match the
  independent oracle, FIFO occupancy peaks at 344 of 512 entries, and the path
  drains exactly. After cache flush, the first qualified candidate produces a
  sticky cache-miss quarantine and no score.

The synthetic IFFT values exercise the downstream fixed-point interfaces but
are not a substitute for generated-XFFT bit-accurate IQ replay. The complete
13-test acquisition RTL suite passes.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the composed
qualifier/FIFO/join/preparation/two-divider top for `xc7z010clg400-1` at 100
MHz. It requires exactly two RAMB36E1s, no RAMB18E1, four DSP48E1s, zero
methodology violations, no nonempty `check_timing` category, nonnegative
setup/hold slack, at most 3,000 LUTs, and at most 2,500 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 1,968 | 1,827 | 2 | 0 | 4 | +0.633 ns | +0.265 ns |

The retained summary is
`reports/starlink-pss15-candidate-score-path-ooc-summary.txt`, SHA-256
`7b40dbc2e4df1b0bc9adc91b8eac07ed388a57c2aad07bce29da2cb745be45a6`.
This is post-opt unplaced slice evidence with modeled 0.5--1.0 ns synchronous
input arrival and 0.0--0.5 ns output delay. The worst reported setup path is an
external `resetn`-to-`ifft_ready` boundary; complete placement/routing and the
real upstream/downstream registers remain mandatory.

An earlier composition that drove every stage's flush combinationally from the
sticky fault missed this same gate by 0.274 ns through 14 control levels. The
final quarantine-plus-explicit-flush contract removes that long feedback path
and is also easier to audit: faults remain visible until the controller begins
recovery.

## Planning resource and rate consequence

The prior 7,720-LUT planning subtotal counted the FIFO, preparation stage, and
two divider lanes as independent OOC sums. Replacing those values with this
single composed result and retaining the two XFFT cores, phase map, overlap
scheduler, spectrum product, and energy cache produces a revised isolated
subtotal of 7,850 LUTs, 11,928 flip-flops, 37.5 of 60 BRAM tiles, and 32 of 80
DSP48E1s. That is approximately 44.6% of LUTs, 33.9% of flip-flops, 62.5% of
BRAM tiles, and 40.0% of DSPs on the Zynq-7010. The coefficient ROM, generated
FFT wrapper/controller, phase/index generator, AXI/CDC/control shell, debug
telemetry, and routing margin remain excluded; additive OOC figures are not a
placed-design utilization claim.

At 100 MHz, one divider lane accepts an item every nine clocks and two lanes
provide 22.22 million scores/s, above the canonical continuous 15 MS/s
candidate rate. One overlap-save block begins every 447 samples, or every 2,980
acquisition clocks at 15 MS/s. The measured 344-entry one-block peak leaves 168
FIFO entries in this simulation, but the generated XFFT cadence and full-shell
backpressure must reproduce that bound before it becomes implementation
headroom evidence.

## Source lock and next gate

The RTL is source-locked at HDL commit
`e12355ec0572c0637932fed0b3846c6a0b52a99c`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-candidate-score-path-v1` on the
experimental do-not-merge branch. Firmware-main guard PR #89 passed all five
required checks and protects that exact gitlink at merge commit
`e1966f5fe20370aa841e16143eb05c94152ea8eb`; the identity is also bound by the
source manifest.

The next implementation gate is the generated-XFFT wrapper/controller and
upper-edge coefficient ROM. It must bind configuration, exponent/TUSER/TLAST,
overflow/event telemetry, block identity, and flush behavior, then pass a
bit-accurate CI16 IQ-to-score replay through scheduler, energy cache, both FFTs,
spectrum product, and this score path. Only after that should the score stream
be connected to the phase map and evaluated in a full routed RX-only shell.
No radio was contacted for this checkpoint.
