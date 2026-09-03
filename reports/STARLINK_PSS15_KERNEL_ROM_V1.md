# Starlink PSS15 hash-locked kernel-ROM checkpoint

## Verdict

PASS for the selected upper-edge 512-bin PSS coefficient ROM and its strict
streaming protocol boundary. The exact artifact is independently hash-locked,
all coefficients pass deterministic RTL replay under backpressure, five
protocol-fault classes fail closed, and the final implementation passes the
canonical Vivado 2022.2 Zynq-7010 100 MHz post-opt out-of-context gate.

This is a source-only experimental checkpoint. It is not eligible to merge,
release, build into a radio image, or persistently flash. It does not
instantiate either generated XFFT core, prove transform arithmetic, accept live
RX IQ, produce a PSS score or timing result, connect the phase map, or qualify
15, 30, or 60 MS/s hardware operation. No radio was contacted.

## Frozen coefficient artifact

The retained memory contains exactly 512 complex signed-Q1.23 coefficients.
Each 48-bit line is packed as `{Q[23:0], I[23:0]}`. The coefficients range from
`-4727221` through `5434212` across both components.

`verify_upper_edge_pss_kernel.py` parses every line without NumPy or a Xilinx
library, rejects anything except 12 lowercase hexadecimal digits, restores
both signed components, and serializes each bin as little-endian signed
32-bit I followed by Q. It binds these independent identities:

| Artifact interpretation | SHA-256 |
|---|---|
| Canonical signed-I/Q byte stream | `d96c56b3d6bcd03419a57f23f3ce4929f1e478663119f5cb5ec9b14327b7ff2b` |
| Exact textual `.mem` file | `7c89ff2a026f5fab91e655ab969ac07c11bf9715215173dadec07084527aea7d` |

The canonical digest independently matches the upper-edge kernel produced by
the already frozen XFFT bit-accurate oracle. This checkpoint retains only the
resulting memory image and its open verifier, not a proprietary C-model file.

## Streaming and fault contract

`starlink_pss_kernel_rom.v` is a one-entry elastic, synchronous-read coefficient
sidecar between the forward-XFFT adapter and the Q1.23 complex spectrum
product. It can accept and publish one bin per 100 MHz clock when unstalled. It
intentionally carries coefficient and transform metadata, not the forward
complex sample itself; the composition gate must register each accepted I/Q
beat beside the lookup and permit the product only when that paired data and
coefficient are both valid. On every accepted beat the ROM requires:

- natural-order indexes `0..511` with TLAST only at index 511;
- one stable five-bit forward block exponent for the complete block;
- one stable 64-bit absolute block-start identity; and
- a next-block start exactly 447 samples after the preceding block.

A malformed beat is consumed but never published. Sequence and metadata
pulses identify the reason, while the sticky protocol fault closes both sides
until the shared acquisition flush. A held output and all its metadata remain
stable under downstream backpressure.

The self-checking simulation replays the complete coefficient table across
three correctly framed blocks, including two consecutive overlap-save block
identities and deterministic output stalls. It verifies 1,539 valid outputs in
total, observes a 512-cycle uninterrupted acceptance run, and separately
injects wrong index, early TLAST, changing exponent, changing block identity,
and wrong next-block stride. Every quarantine is explicitly flushed and the
final valid lookup proves recovery. The acquisition regression now contains
15 passing RTL simulations.

## OOC implementation gate

The first implementation deliberately failed the resource requirement: two
separate I/Q slice expressions caused Vivado to duplicate the constant table
as LUT ROMs. Combining them into one registered 48-bit memory read produced
the intended block-ROM implementation without changing the streaming result.

The final Vivado 2022.2 post-opt, unplaced OOC result at 100 MHz on
`xc7z010clg400-1` is:

| Resource/check | Result |
|---|---:|
| LUT | 88 |
| Registers | 229 |
| RAMB36E1 / RAMB18E1 | 0 / 2 |
| Equivalent BRAM tiles | 1.0 |
| Nonzero BRAM `INIT_xx` words | 128 |
| DSP48E1 | 0 |
| Setup WNS | +3.634 ns |
| Hold WHS | +0.056 ns |
| Methodology violations | 0 |
| Nonzero `check_timing` categories | 0 |

The frozen summary is
`reports/starlink-pss15-kernel-rom-ooc-summary.txt`, SHA-256
`a0129ef6fc12c441fd8562ddd24dd98399f0b25075157702ac88b4360b36d32d`.
This is not routed-shell timing evidence; the positive but narrow OOC hold
margin remains an explicit full-composition route check.

Adding this boundary to the prior isolated subtotal yields 8,144 LUTs, 12,379
registers, 38.5 BRAM tiles, and 32 DSP48E1s: 46.3%, 35.2%, 64.2%, and 40.0%
of the Zynq-7010, respectively. These are additive OOC planning numbers, not a
placed-and-routed utilization claim. They still exclude generated-XFFT
composition control, CI16 conversion, phase generation and map wiring,
AXI/CDC/control, debug telemetry, and route margin.

## Source lock and next gate

The source is locked at HDL commit
`a7985ea3ab5b5b867caf8a34f72601c816874041`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-kernel-rom-v1` on the experimental
do-not-merge branch. Firmware-main guard PR #91 passed all five required checks
and protects only that exact HDL gitlink identity at merge commit
`250fc46cc57f38aec6a8321990f84460fb73d749`; the experimental detector source
itself remains outside firmware main.

The next gate is replay-only composition: deterministically recreate and
instantiate the two frozen 512-point XFFT cores, convert scheduler CI16 samples
to Q1.23, add an explicit one-entry forward-I/Q/ROM join, connect the spectrum
product to the inverse adapter and candidate-score tail, and compare every
intermediate plus all 447 normalized results with the frozen oracle. Phase-map
connection, full RX-shell routing, and exact-radio qualification remain later
gates.
