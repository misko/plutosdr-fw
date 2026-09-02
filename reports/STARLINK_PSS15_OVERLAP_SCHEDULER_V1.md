# Starlink PSS15 overlap-save scheduler checkpoint

Status: **experimental IP-independent RTL; do not merge, build into a radio
image, release, or persistently flash**.

This checkpoint implements the first continuous-IQ hardware slice between the
accepted RX sample tap and the selected 512-point XFFT pair. It does not yet
instantiate FFT IP, multiply by a PSS kernel, normalize a score, feed the phase
map, integrate the RX-only shell, or claim a PSS detection.

## Streaming contract

The scheduler accepts a non-backpressured CI16 stream with an explicit gap bit
and a 64-bit absolute accepted-sample index. At the canonical 15 MS/s geometry
it retains 2,048 complex samples, emits 512-sample FFT frames, overlaps 65
samples, and advances each frame by 447 new samples. Each frame carries its
absolute start index, positions 0 through 511, and an exact last marker.

The ring has one write path from the RX tap and one registered read path toward
the FFT. A four-entry descriptor FIFO decouples the continuous writer from FFT
ready/valid stalls. The first frame is available after 512 accepted samples;
later frames become available every 447 samples, or every 29.8 us at 15 MS/s.
This matches the separately frozen per-core transform-rate requirement of
17.1812 MS/s.

Continuity fails closed. Disable, an explicit gap, a nonconsecutive absolute
index, a full descriptor queue, or an imminent overwrite of the oldest needed
ring sample aborts the active and queued frames. For a valid discontinuity or
overflow sample, that current sample is retained as sample zero of a new
segment. No partial pre-failure block can complete after the restart. Separate
one-cycle status pulses distinguish gap, index, and capacity failures.

## Deterministic simulation

`hdl/library/starlink_pss_acquisition/run_tests.sh` now runs the existing phase
map test plus two self-checking scheduler testbenches.

The default-geometry test drives 3,500 continuous indexed samples at alternating
six/seven-clock periods under independent output stalls. It verifies seven
overlapping frames sample-for-sample, output stability under backpressure, and
then an eighth frame whose first sample is an explicit gap restart. Every frame
start advances by exactly 447 and every frame contains exactly 512 ordered CI16
samples.

The lifecycle test uses deliberately small geometries to reach corner cases
quickly. It proves normal overlap, disable during an unaccepted output, queue
overflow, ring-retention overflow, absolute-index restart, explicit-gap
restart, exact post-restart samples, and event/completion accounting. Both
geometries pass under Icarus Verilog with `-g2012 -Wall`.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the default
512/65/447 geometry for `xc7z010clg400-1` at 100 MHz. It requires exactly two
RAMB36E1 blocks, zero RAMB18E1 and DSP48E1 blocks, no methodology violation, no
nonempty `check_timing` category, nonnegative setup/hold slack, at most 400
LUTs, and at most 800 flip-flops.

| LUT | FF | RAMB36E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|
| 273 | 695 | 2 | 0 | +2.012 ns | +0.011 ns |

The retained summary is
`reports/starlink-pss15-overlap-scheduler-ooc-summary.txt`, SHA-256
`37682496c3f6edcee513c6c775aa42e0a5837defd5da98b791eda88baa4a60b3`.
This is post-opt unplaced slice evidence; only complete-shell placement and
routing can qualify the composed detector.

The RTL is source-locked at HDL commit
`2c9e564350e1c42d9aa5b14e7ee61929a754f1fd`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-overlap-scheduler-v1` on the
experimental do-not-merge branch. Firmware-main guard PR #83 protects that
exact gitlink; all five checks passed and it merged as
`fed8a275c21abac4360b2a55a2f0bda8828efa4e` before this experimental parent
advanced to it.

## Resource and rate consequence

Adding this scheduler to the two measured XFFT cores and the one-template phase
map raises the isolated planning subtotal from 4,920 to 5,193 LUTs, 8,416 to
9,111 flip-flops, and 31 to 33 of 60 BRAM tiles; DSP use remains 18. The complex
spectrum multiplier, energy window, correlation/output FIFO, exact rational
normalizer, AXI/CDC shell, and routing margin are still absent. These additive
figures are planning evidence only and do not waive the 15% full-route headroom
gate.

At 30 and 60 MS/s, continuous acquisition still uses the canonical 15 MS/s
engine behind separately qualified x2 and x4 DDC lanes. This scheduler then
retains the same 512/65/447 geometry and source-index contract; the DDC owns the
full-rate-to-15-MS/s phase and group-delay mapping. The sparse confirmation
tracker and ordinary RX DMA remain at the full input rate. This checkpoint is
therefore not 30/60 MS/s qualification.

## Next implementation gate

Bind behavioral forward/inverse FFT interfaces to the selected generated XFFT
configuration, then implement the Q1.23 spectrum product, block-exponent
restoration, sliding input energy, valid-output FIFO, and exact rational
eight-bit score conversion. A self-checking IQ-to-score replay must preserve the
frozen maximum one-count score error and exact phase/cadence/classification
decisions before the existing phase map is connected. Only after combined OOC,
complete RX-only route, detector-disabled DMA regression, and source locking may
a RAM-only hardware-injection image be considered. No radio was contacted for
this checkpoint.
