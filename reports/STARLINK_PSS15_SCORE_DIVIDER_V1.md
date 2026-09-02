# Starlink PSS15 exact score-divider checkpoint

Status: **experimental normalization-slice RTL; do not merge, build into a
radio image, release, or persistently flash**.

This checkpoint implements one exact rational quantization lane. It does not
square an IFFT correlation, restore either block-floating exponent, form the
energy/coefficient denominator, join the energy cache, instantiate the raw
result FIFO or second lane, feed the phase map, integrate the RX-only shell, or
claim PSS timing.

## Exact score contract

For each accepted unsigned 69-bit numerator `N` and denominator `D`, the lane
returns zero if either operand is zero, 255 if `N >= D`, and otherwise returns
`round_ties_even(255*N/D)`. The implementation is an eight-step restoring
divider: it calculates only the eight quotient bits needed by the score, then
uses the exact final remainder and original denominator to round once. It does
not approximate a reciprocal or use floating point.

All inputs, including zero and saturation cases, occupy the same eight
calculation iterations. The lane preserves its 64-bit candidate-start index,
holds a completed output stable under backpressure, and accepts no new item
while its calculation or unaccepted output is live. Reset or flush discards an
in-progress or stalled completed result without publishing partial state.
Accepted, completed, and zero-denominator pulses make accounting explicit.

One lane has a nine-clock acceptance interval: one acceptance clock followed
by eight calculation clocks. Two fixed-latency lanes with alternating dispatch
therefore have 22.22 million-score/s aggregate capacity at 100 MHz. That is
above the canonical 15 million candidate scores/s; the later ordered merger
must still prove that stalls cannot reorder the two lanes.

## Deterministic RTL simulation

An independent standard-library Python generator computes the exact integer
oracle. The retained default suite checks 4,112 cases: 16 directed boundaries
and 4,096 deterministic full-width random ratios. Directed values include
zero numerator, zero denominator, `N == D`, `N > D`, both full-width extrema,
and half-way cases whose truncated quotient is alternately even and odd.

The self-checking SystemVerilog test compares every score and candidate index,
checks denominator-zero metadata and pulse counts, continuously drives inputs
through calculation backpressure, stalls completed outputs, and proves output
stability. It also flushes one item partway through division and another after
completion while the output is stalled. The complete acquisition RTL suite,
including all five preceding slices, passes.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes one default 69-bit,
eight-bit-score lane for `xc7z010clg400-1` at 100 MHz. It requires no BRAM or
DSP48E1, no methodology violation, no nonempty `check_timing` category,
nonnegative setup/hold slack, at most 1,500 LUTs, and at most 1,000 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 599 | 378 | 0 | 0 | 0 | +0.962 ns | +0.284 ns |

The retained summary is
`reports/starlink-pss15-score-divider-ooc-summary.txt`, SHA-256
`01be7ab19505f349e420825a412cb73038609ab3a4b96d0f12471e3469610374`.
This is post-opt unplaced slice evidence. Only composed placement and routing
can qualify the two-lane timing and available shell headroom.

The RTL is source-locked at HDL commit
`8755d94eefb65cba6155a28c8a4c9c3f2ec69e41`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-score-divider-v1` on the experimental
do-not-merge branch. Firmware-main guard PR #86 protects that exact gitlink;
all five checks passed and it merged as
`0c6f96ef4d95426da4c62a4b30828e5535b7b5c4` before this experimental parent
advanced to it.

## Resource and rate consequence

Adding two measured lanes to the two XFFT cores, phase map, overlap scheduler,
spectrum product, and energy cache raises the isolated planning subtotal from
5,882 to 7,080 LUTs and 10,101 to 10,857 flip-flops, while retaining 35.5 of 60
BRAM tiles and 28 of 80 DSP48E1s. The coefficient ROM, FFT binding/controller,
raw-result FIFO, wide exponent-aware score preprocessor, dispatcher/ordered
merge, AXI/CDC shell, and route margin remain absent. Additive OOC results are
planning evidence only.

The lane runs in the canonical 100 MHz acquisition domain and its capacity is
stated only for the Stage-15 score rate. Future x2/x4 DDC lanes for 30/60 MS/s
must reduce to the same canonical score stream or provide separately proven
additional divider capacity; this checkpoint authorizes neither stage.

## Next implementation gate

The next independent slice forms the exact ratio. It squares the signed Q1.23
IFFT real and imaginary outputs, restores power by
`2^(2*(1 + Ef + Ei))`, and multiplies the 38-bit sample energy by the frozen
31-bit coefficient energy. Any value that cannot be represented in the
69-bit ratio interface must saturate in a way that is exactly equivalent to
`N >= D`, never wrap. A cross-language test must cover every exponent boundary,
signed extrema, denominator extrema, saturation, stalls, and flush before the
raw-result FIFO and energy-cache join are added. No radio was contacted for
this checkpoint.
