# Starlink PSS15 sliding-energy cache checkpoint

Status: **experimental denominator-path RTL; do not merge, build into a radio
image, release, or persistently flash**.

This checkpoint implements the sample-energy half of normalized PSS scoring.
It does not instantiate FFT IP, join an IFFT correlation to an energy value,
calculate an eight-bit score, feed the phase map, integrate the RX-only shell,
or claim PSS timing.

## Exact energy and retention contract

For each contiguous 66-sample CI16 window, the module calculates
`sum(I^2 + Q^2)` exactly. One signed 16-by-16 square is mapped to each of two
DSP48E1s; every per-sample power is an unsigned 32-bit value and the rolling
window is an unsigned 38-bit value. The 66-entry power history is not reset as
bulk state. A count and segment lifecycle make unread history irrelevant until
the new window is complete.

Every complete energy is written by its 64-bit absolute candidate-start index
into a 2,048-entry circular memory. The cache retains explicit oldest/newest
absolute indexes, so a low-address alias outside the live range cannot be
accepted. It has an independent ready/valid lookup port for the later IFFT
join. A request for the energy written on the same clock is served by an exact
registered bypass. A request for the oldest entry on its overwrite clock
returns `found=0`, avoiding device-dependent block-RAM read/write behavior.

The nonbackpressured sample input carries an explicit gap bit and an absolute
accepted-sample index. Gap, nonconsecutive index, flush, and disable invalidate
the partial window, retained range, and any unaccepted lookup response. The
current gap/discontinuity sample becomes sample zero of a new segment. BRAM
contents are not bulk-cleared; invalid range metadata makes them unreachable.

## Deterministic RTL simulation

The self-checking default-geometry test drives 2,500 samples at alternating
six/seven-clock periods, approximately 15 MS/s at the 100 MHz acquisition
clock. Its first sample exercises the asymmetric signed CI16 extrema. All
2,435 initial window energies and absolute indexes are recomputed independently
inside the testbench and compare exactly.

The test then proves 2,048-entry rollover, exact oldest/newest lookup, stale and
future miss handling, response stability under stalls, same-cycle newest-value
bypass, and fail-closed oldest-value overwrite collision. It additionally
flushes a stalled response with an explicit gap, rebuilds five complete
energies, restarts again on an index discontinuity, rebuilds one complete
energy, and checks disable invalidation. In total, all 2,443 emitted energies
compare exactly and lifecycle/miss pulse accounting passes.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the default 66/2048
geometry for `xc7z010clg400-1` at 100 MHz. It requires exactly two RAMB36E1
plus one RAMB18E1 (2.5 BRAM tiles), exactly two DSP48E1s, no methodology
violation, no nonempty `check_timing` category, nonnegative setup/hold slack,
at most 1,000 LUTs, and at most 800 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 469 | 534 | 2 | 1 | 2 | +1.960 ns | +0.056 ns |

The retained summary is
`reports/starlink-pss15-energy-cache-ooc-summary.txt`, SHA-256
`f0720542c1f2dddb86b1717ecb4d0b6b76d61ec431c2b6d4f1688c59f3ae456c`.
This is post-opt unplaced slice evidence. Only composed placement and routing
can qualify lookup timing and resource headroom beside the FFT pair and phase
map.

The RTL is source-locked at HDL commit
`8282a4a7b2aef1ff05f40f2342cca71e20521fd5`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-energy-cache-v1` on the experimental
do-not-merge branch. Firmware-main guard PR #85 protects that exact gitlink
with all five checks passing; it merged as
`dfe129b6eed7c7d9adbe4bd1d5451442284dce81` before this experimental parent
advanced to it.

## Resource and rate consequence

Adding the energy cache to the two measured XFFT cores, phase map, overlap
scheduler, and spectrum product raises the isolated planning subtotal from
5,413 to 5,882 LUTs, 9,567 to 10,101 flip-flops, 33 to 35.5 of 60 BRAM tiles,
and 26 to 28 of 80 DSP48E1s. The coefficient ROM, FFT binding/controller,
inverse-result FIFO, exponent restoration, exact rational normalizer, AXI/CDC
shell, and route margin remain absent. Additive OOC results are planning
evidence only.

The cache runs on the canonical 15 MS/s sample/index domain. Future x2/x4 DDC
lanes for 30/60 MS/s must present contiguous canonical indexes with a frozen
full-rate timing map; this checkpoint does not authorize either stage.

## Next implementation gate

The next independent slice is the correlation-result FIFO and exact score
normalizer. Its request index must equal `block_start + ifft_index - 65`; a
cache miss, FFT event, gap, overflow, or metadata mismatch must flush the
entire in-flight block. A cross-language test must prove exact energy/
correlation joins and all rational rounding boundaries before the phase map is
connected. No radio was contacted for this checkpoint.
