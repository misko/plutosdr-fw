# Starlink PSS15 spectrum-product checkpoint

Status: **experimental arithmetic RTL; do not merge, build into a radio image,
release, or persistently flash**.

This checkpoint implements the exact fixed-point bridge between the selected
forward and inverse 512-point FFTs. It does not instantiate either generated
FFT core, package the PSS coefficient ROM, calculate input energy or a
normalized score, feed the phase map, integrate an RX-only shell, or claim PSS
timing.

## Arithmetic and streaming contract

The input spectrum and precomputed kernel are signed 24-bit Q1.23 complex
values. Four signed 24-by-24 products form the exact 49-bit complex result. The
result is divided by 2^24: 23 fractional bits plus the one-bit safety shift
frozen by the bit-accurate XFFT replay. Signed rounding is nearest with ties to
even, followed by 24-bit saturation and a per-result overflow flag/pulse.

The three-stage elastic pipeline accepts one bin per 100 MHz clock when the
downstream is ready. It carries the 9-bit transform-bin index, 5-bit forward
block exponent, last marker, and 64-bit absolute block start without
reinterpretation. Every output remains stable under backpressure. Synchronous
flush invalidates all three stages, deasserts input-ready during the flush, and
prevents a pre-gap product from surviving into a restarted stream.

## Deterministic bit-exact replay

`hdl/library/starlink_pss_acquisition/run_tests.sh` generates 4,112 vectors
with a standard-library-only Python oracle and replays them through a
self-checking SystemVerilog testbench. Sixteen directed cases cover zero,
positive and negative half-way rounding, signed extremes, saturation, and a
mixed complex product; 4,096 additional cases use a frozen random seed over
the full signed input range.

The replay compares both 24-bit components and the overflow indication exactly,
checks every metadata field and output order, drives sustained ready/valid
stalls until input backpressure occurs, proves all fields remain stable while
stalled, and flushes a result already resident at an unaccepted output. All
4,112 vectors pass. One deliberately extreme vector saturates; the frozen real
capture replay separately reports zero modeled product overflow.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the product for
`xc7z010clg400-1` at 100 MHz. It requires exactly eight DSP48E1 cells, no BRAM,
no methodology violation, no nonempty `check_timing` category, nonnegative
setup/hold slack, at most 1,200 LUTs, and at most 1,000 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 220 | 456 | 0 | 0 | 8 | +2.362 ns | +0.284 ns |

The retained summary is
`reports/starlink-pss15-spectrum-product-ooc-summary.txt`, SHA-256
`4939369a6d6f2e10e98b0583c6efaa76f18feb6feac1df271f60b11aa48f5ac4`.
This is post-opt unplaced slice evidence; it does not establish timing or
headroom after the FFT pair, ROM, score path, AXI/CDC boundary, and shell are
composed and routed.

The RTL is source-locked at HDL commit
`5b2cdd3ba81e98ab3f752f334a34054d0b48f237`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-spectrum-product-v1` on the
experimental do-not-merge branch. Firmware-main guard PR #84 protects that
exact gitlink; all five checks passed and it merged as
`60169ef8c35cca1ce18c062625141c78a4bb2d3b` before this experimental parent
advanced to it.

## Resource and rate consequence

Adding the product to the two measured XFFT cores, one-template phase map, and
overlap scheduler raises the isolated planning subtotal from 5,193 LUTs to
5,413 LUTs, 9,111 to 9,567 flip-flops, and 18 to 26 DSP48E1s. BRAM remains 33
of 60 tiles. The input-energy window, inverse-output buffering, block-exponent
restoration, exact rational normalizer, AXI/CDC shell, and route margin remain
absent. These additive OOC figures are planning evidence only.

At 30 and 60 MS/s, this arithmetic remains a one-bin-per-clock 15 MS/s engine
behind separately qualified x2 and x4 DDC lanes. It does not authorize either
higher-rate stage. The DDCs must preserve the full-rate-to-canonical timing
map; the ordinary RX DMA and sparse full-rate confirmation tracker remain
separate consumers.

## Next implementation gate

The next safe composition step is a simulation wrapper around behavioral FFT
interfaces, the frozen kernel ROM image, this product, inverse-output metadata,
and block-exponent restoration. In parallel with that wrapper, the 66-sample
CI16 sliding-energy path and result FIFO can be proven independently. Only an
end-to-end IQ-to-eight-bit-score replay may connect normalized scores to the
existing phase map. No radio was contacted for this checkpoint.
