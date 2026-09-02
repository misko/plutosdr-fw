# Starlink PSS15 exact score-ratio preparation checkpoint

Status: **experimental normalization-arithmetic RTL; do not merge, build into
a radio image, release, or persistently flash**.

This checkpoint implements the wide arithmetic between a joined IFFT/energy
item and the exact divider lanes. It does not instantiate the raw IFFT-result
FIFO, request the energy cache, dispatch two dividers, merge scores, bind FFT
IP, feed the phase map, integrate the RX-only shell, or claim PSS timing.

## Exact ratio contract

The finite-width XFFT oracle returns signed 24-bit Q1.23 correlation components
and five-bit forward/inverse block exponents `Ef` and `Ei`. For each joined
38-bit sample energy `Ex`, the pipeline calculates:

```text
C2 = C_re*C_re + C_im*C_im
N  = C2 * 2^(2*(1 + Ef + Ei))
D  = Ex * 1073742825
```

The default coefficient energy is frozen at `1073742825` for the selected
upper-edge Stage-15 template. The lower-edge template energy is `1073776498`.
The RTL parameter can represent it, but this checkpoint does not authorize the
lower-edge configuration: it requires its own parameter-override replay and
OOC gate. The two signed 24-by-24 squares and 48-bit sum are exact.
The coefficient/sample product is an unsigned 38-by-31-bit value and therefore
fits the 69-bit divider interface.

If mathematical `N` fits 69 bits it is emitted exactly. If it is wider, the
emitted numerator is all ones and a saturation flag/pulse is asserted. That is
not an arithmetic approximation: every representable denominator is less than
the all-ones numerator, so the downstream divider returns the same saturated
score 255 as it would for an unbounded `N >= D`. Zero energy remains an exact
zero denominator and therefore produces score zero downstream. No wide value
is allowed to wrap.

The three-stage elastic ready/valid pipeline sustains one accepted item per
clock, preserves the 64-bit candidate-start index and the exact power shift,
holds every output stable under backpressure, and flushes all in-flight and
stalled-output state without publication. Accepted, completed, numerator-
saturation, and zero-denominator pulses provide explicit accounting.

## Deterministic RTL simulation

An independent standard-library Python generator computes each square,
unbounded shifted numerator, saturation decision, and denominator using Python
integers. The retained suite checks 4,112 items: 16 directed boundaries and
4,096 deterministic full-width random cases. One quarter of the random cases
uses the observed `Ef/Ei` range `0..2`; the rest spans the full five-bit input
range `0..31`.

The directed and random corpus covers signed Q1.23 extrema, zero and maximum
38-bit energy, zero correlations, first fitting and overflowing shifts, full
exponent extremes, and 2,862 deliberate numerator saturations. Two items have
zero denominator. The self-checking SystemVerilog test compares every output
bit and candidate index, drives sustained elastic backpressure, checks output
stability and all pulse counts, flushes a middle-stage item, and flushes a
completed output while stalled. The complete acquisition RTL suite passes.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the default pipeline
for `xc7z010clg400-1` at 100 MHz. It requires exactly four DSP48E1s, no BRAM,
no methodology violation, no nonempty `check_timing` category, nonnegative
setup/hold slack, at most 2,000 LUTs, and at most 1,200 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 561 | 581 | 0 | 0 | 4 | +0.396 ns | +0.269 ns |

The two 24-bit squarers each map to a two-DSP cascade. The sparse selected
upper-edge coefficient product maps into logic and consumes no DSP. The retained summary
is `reports/starlink-pss15-score-prepare-ooc-summary.txt`, SHA-256
`b2f50c5122f2341e3569844e902e488943ac763507e04300d1e5c1e495ac6311`.

This is post-opt unplaced slice evidence. Its +0.396 ns setup margin is positive
but deliberately treated as a complete-shell route risk. It is not evidence
that the composed FFT/FIFO/normalizer path routes at 100 MHz.

The RTL is source-locked at HDL commit
`078e725389c8c790e1f3c3c612b242697f87de77`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-score-prepare-v1` on the experimental
do-not-merge branch. Firmware-main guard PR #87 protects that exact gitlink;
all five checks passed and it merged as
`bfb0247a374724efde0589dcb259bb1396cf4abd` before this experimental parent
advanced to it.

## Resource and rate consequence

Adding the preparation pipeline to the two XFFT cores, phase map, overlap
scheduler, spectrum product, energy cache, and two score-divider lanes raises
the isolated planning subtotal from 7,080 to 7,641 LUTs, 10,857 to 11,438
flip-flops, and 28 to 32 of 80 DSP48E1s, while retaining 35.5 of 60 BRAM tiles.
The coefficient ROM, FFT binding/controller, raw-result FIFO, indexed-energy
join, dispatcher/ordered merge, AXI/CDC shell, and route margin remain absent.
Additive OOC results are planning evidence only.

The pipeline has one-result-per-clock capacity, so it is not the Stage-15
throughput limiter. Future x2/x4 DDC lanes at 30/60 MS/s still feed the same
canonical 15 MS/s acquisition stream; their arithmetic and full-rate timestamp
mapping remain independent qualification gates.

## Next implementation gate

The next slice is a 512-entry raw-result FIFO and indexed-energy join. It must
accept each valid IFFT result burst without backpressuring the XFFT core, store
signed correlation plus both block exponents and absolute candidate identity,
request exactly that index from the energy cache, and fail the entire in-flight
block closed on a cache miss, FFT event, metadata mismatch, FIFO overflow,
gap, disable, or flush. Only then may this pipeline feed two alternating exact
divider lanes and an explicitly ordered ready/valid merger. No radio was
contacted for this checkpoint.
