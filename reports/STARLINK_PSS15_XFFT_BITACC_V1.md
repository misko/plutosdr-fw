# Starlink PSS15 XFFT finite-width arithmetic checkpoint

Status: **offline arithmetic candidate; not RTL integration, routed detector,
radio evidence, or live-PSS qualification**.

This checkpoint selects and tests the finite-width arithmetic for the IQ-to-
correlation part of continuous 15 MS/s acquisition. It uses the bit-accurate
Xilinx FFT v9.1 C model installed by Vivado 2022.2; no Xilinx library, header,
or generated IP is copied into source control.

## Selected arithmetic

The retained candidate is a dedicated forward/inverse pair of 512-point,
radix-4 burst XFFT cores. Both use 24-bit fixed-point data, 16-bit phase
factors, block-floating scaling, convergent rounding, and natural-order output.
The fixed PSS-kernel transform uses scaling schedule `(2, 0, 0, 0, 0)`. The
frequency-domain complex product is rounded ties-to-even to Q1.23 after one
safety shift.

Each block accepts 512 IQ samples and emits 447 valid correlations after the
first 65 circular-convolution outputs are discarded. If the forward and
inverse block exponents are `Ef` and `Ei`, an inverse-output Q1.23 integer is
returned to the CI16/Q1.15 correlation scale by exactly `2^(1 + Ef + Ei)`.
The existing exact rational score conversion then produces one eight-bit score
per candidate start.

The precomputed lower- and upper-edge kernel digests use interleaved signed
32-bit little-endian storage of the Q1.23 integers:

| Edge | Kernel SHA-256 |
|---|---|
| lower | `ba7189f2648e62116a49b51028ae08671ae3856fff5dc4f6965611eeaa967f33` |
| upper | `d96c56b3d6bcd03419a57f23f3ce4929f1e478663119f5cb5ec9b14327b7ff2b` |

The first hardware image enables one selected edge-template bank at a time.
Searching both edges concurrently would duplicate the inverse path and the
20-RAMB36 ping-pong map, consuming most Zynq-7010 block RAM before integration.
Edge selection is therefore bound to the RF tuning plan; it is not silently
maximized across two templates.

## Why 24-bit block floating

A conservative fixed-scale 16-bit chain lost two score counts on some perfect
PSS placements. A 16-bit block-floating chain restored all structural peaks to
255 but moved up to one score count on roughly 0.6--6.3% of the three real
captures. The selected 24-bit block-floating chain keeps every tested
structural boundary peak at 255 and reduced the real-corpus difference to 2,881
of 12,582,717 scores, or 0.02290%. Every difference is exactly one count or
less.

The XFFT path is finite-width and is not mislabeled bit-exact to the direct
integer correlator. Its acceptance contract is instead explicit: maximum
per-score error one, zero arithmetic overflow, and exactly equal final phase,
cadence hypothesis, and pass/reject classification on every frozen capture.
The candidate-gated direct correlator remains the exact confirmation stage.

## Frozen real replay

All figures use 20,000 one-sample phase bins, 64 frames per map, and the frozen
`+/-10 ppm` cadence bank. The bit-accurate and exact-integer candidates are
identical in every row.

| Input | Scores | Scores changed | Max delta | Map max delta | Phase | Drift/tile | Robust z | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| primary positive | 4,194,239 | 656 | 1 | 2 | 1,173 | +12 | 12.549 | pass |
| weaker positive | 3,145,663 | 922 | 1 | 2 | 2,755 | 0 | 6.205 | pass |
| independent RF negative | 5,242,815 | 1,303 | 1 | 2 | 10,646 | +12 | 4.561 | reject |

The 24-bit model reports zero forward, inverse, or spectrum-product overflows.
Unit tests also cover random CI16 equality, both template-kernel digests, starts
before/at/after the 447-result overlap boundary, zero energy, signed convergent
rounding, a full-range constant input, and refusal of an unpinned C-model
archive.

The machine-readable replay is
`reports/starlink-pss15-xfft-bitacc-v1.json`, SHA-256
`2b2f54c37461a653f6c50bf5c68fec769b3b8fb6d300d82859de75949ab01a87`.
It binds the installed XFFT archive SHA-256
`0f264e0e15f93fcf5df9c60e715fe51c9bcd9639b578a5ae67be4df5cf2d5f87`.

## Generated core estimate

`tools/run_starlink_xfft24_ooc.sh` recreates one core for
`xc7z010clg400-1`, checks that the 20 MS/s request selected radix-4 burst, and
gates resources and 100 MHz post-synthesis timing:

| LUT | FF | RAMB18E1 | BRAM tiles | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 2,189 | 3,847 | 11 | 5.5 | 9 | +6.411 ns | +0.203 ns |

The required sustained transform input rate per core is
`512 / 447 * 15 MS/s = 17.1812 MS/s`, below the generated 20 MS/s target. Two
dedicated cores total 4,378 LUTs, 7,694 FFs, 11 BRAM tiles, and 18 DSPs before
the spectrum multiplier, input/score FIFOs, energy window, and normalizer. With
the already measured one-template phase map, those isolated blocks total 4,920
LUTs, 8,416 FFs, and 31 of 60 BRAM tiles. These are additive planning numbers,
not a substitute for complete-shell placement and routing.

The retained OOC summary is
`reports/starlink-pss15-xfft24-ooc-summary.txt`, SHA-256
`c96095a10f07739358c38ff3ae55cb0879ce42c0ae019499dc3bf9de69a3f5c1`.

## Next implementation gate

The next slice is an IP-independent overlap-save scheduler with behavioral FFT
interfaces. It must prove uninterrupted sample admission, exact 65-sample
overlap, block exponents, natural-order bins, kernel addressing, valid output
indexes, gap/disable flush, and no score duplication or omission. Only then is
the generated XFFT bound into the RTL. A 512-entry result FIFO feeds two
interleaved exact eight-step normalized-score dividers; their aggregate 25
million scores/s exceeds 15 MS/s and their FIFO absorbs the 447-cycle inverse
FFT burst. Full IQ-to-score replay, combined OOC, full route, and RAM-only radio
testing remain later gates.
