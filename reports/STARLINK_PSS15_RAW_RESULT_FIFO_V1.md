# Starlink PSS15 raw IFFT-result FIFO checkpoint

Status: **experimental burst-buffer RTL; do not merge, build into a radio
image, release, or persistently flash**.

This checkpoint implements storage for qualified overlap-save IFFT results. It
does not qualify/discard IFFT indexes, request the energy cache, form ratios,
dispatch the divider lanes, merge scores, bind FFT IP, feed the phase map,
integrate the RX-only shell, or claim PSS timing.

## Exact storage contract

Each 123-bit FIFO payload retains the signed Q1.23 correlation real/imaginary
components, five-bit forward and inverse XFFT block exponents, 64-bit absolute
candidate-start index, and block-last marker. The default FIFO contains 512
declared entries. Its block RAM holds queued entries behind one registered
prefetch/output stage; the occupancy count includes that stage, so the visible
capacity remains exactly 512 rather than silently becoming 513.

The FIFO presents ready/valid interfaces on both sides. A simultaneous output
acceptance permits a replacement input at full occupancy. An input presented
without ready raises an overflow pulse but cannot advance the write pointer or
mutate queued data. Reset or flush invalidates pointers, counts, and the output
stage without bulk-clearing block RAM. Accepted and emitted pulses expose
exact traffic accounting, and a maximum-occupancy counter supports later burst
headroom evidence.

This slice deliberately stores the raw 123-bit item rather than the later pair
of 69-bit numerator/denominator values. That keeps 512 entries in two RAMB36
tiles. The indexed sample energy is fetched only when an item drains toward the
score-preparation and divider lanes.

## Deterministic RTL simulation

The self-checking SystemVerilog test first holds the consumer completely
stalled and presents all 447 qualified results from one 512-point overlap-save
block on consecutive clocks. No input backpressure is permitted; visible and
maximum occupancy must both equal 447. The test then drains the block through
output stalls and compares every correlation, exponent, absolute index, last
marker, and pulse in order.

A second phase checks 1,200 transfers with concurrent input/output and
deterministic backpressure. A third fills all 512 declared entries, confirms
ready deassertion, presents a 513th item, and verifies exactly one overflow
without count/state mutation. A final flush must make all retained entries and
the stalled output unreachable. The complete acquisition RTL suite passes.

## Zynq-7010 OOC evidence

The canonical Vivado 2022.2 gate synthesizes and optimizes the default
512-by-123-bit FIFO for `xc7z010clg400-1` at 100 MHz. It requires exactly two
RAMB36E1s, no RAMB18E1 or DSP48E1, no methodology violation, no nonempty
`check_timing` category, nonnegative setup/hold slack, at most 500 LUTs, and at
most 400 flip-flops.

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 79 | 42 | 2 | 0 | 0 | +3.342 ns | +0.011 ns |

The retained summary is
`reports/starlink-pss15-raw-result-fifo-ooc-summary.txt`, SHA-256
`8226e38e2c7739350173a335129cd2398e4eb038091fc7d1ea6312f70abe5a38`.
This is post-opt unplaced slice evidence. The +0.011 ns hold margin is positive
but intentionally treated as a complete-shell post-route risk, not rounded
into a more reassuring number.

The RTL is source-locked at HDL commit
`7cba0eac1cd83e29846b812caca0f0dfee2523d4`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-raw-result-fifo-v1` on the experimental
do-not-merge branch. Firmware-main guard PR #88 passed all five required checks
and protects that exact gitlink in merge commit
`627f1f48e776e174095d34822a8ce3506ed0aebb`; the identity is bound by the
source manifest.

## Resource and rate consequence

Adding the FIFO to the two XFFT cores, phase map, overlap scheduler, spectrum
product, energy cache, score preparation, and two score-divider lanes raises
the isolated planning subtotal from 7,641 to 7,720 LUTs, 11,438 to 11,480
flip-flops, and 35.5 to 37.5 of 60 BRAM tiles, while retaining 32 of 80
DSP48E1s. The coefficient ROM, FFT binding/controller, IFFT qualifier,
indexed-energy join, dispatcher/ordered merge, AXI/CDC shell, and route margin
remain absent. Additive OOC results are planning evidence only.

At 15 MS/s, overlap-save blocks begin every 447 accepted samples, or every
2,980 acquisition clocks at 100 MHz. The inverse core emits its 447 qualified
results as a dense burst; this FIFO absorbs the entire burst even if no result
drains during it. The planned two dividers drain at 22.22 million scores/s on
average, above the continuous 15 million-score/s input rate. Composition must
still measure occupancy using the real XFFT timing rather than relying only on
this arithmetic argument.

## Next implementation gate

The next slice qualifies IFFT indexes 65 through 511, assigns candidate index
`block_start + ifft_index - 65`, drains this FIFO into matching absolute-index
energy-cache lookups, and carries the raw metadata in lockstep with the
one-cycle cache response. A miss, index mismatch, FFT event, overflow, gap,
disable, or flush must fault and invalidate the entire in-flight acquisition
segment; it must never be converted into a zero score. No radio was contacted
for this checkpoint.
