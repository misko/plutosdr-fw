# Starlink PSS acquisition-oracle v1 architecture checkpoint

Status: **offline candidate architecture; not live-PSS or hardware evidence**.

This checkpoint evaluates the continuous 15 MS/s acquisition reduction proposed
for the experimental RX-only firmware.  It does not change the existing exact
tracker, qualify an RTL FFT, contact a radio, decode SSS, or establish Starlink
identity.

## Contract

`tests/starlink_oracle/acquisition.py` defines
`starlink-pss-acquisition-oracle-v1`:

- 512-sample overlap-save processing with 66 Q1.15 PSS taps and 447 valid
  outputs per transform;
- rounded integer correlations checked against the exact direct-dot-product
  oracle;
- exact rational, ties-to-even normalized-power quantization;
- one score for every 15 MS/s candidate start;
- one maximum per phase bin and frame, followed by an exact inter-frame sum;
- complete tiles only, with partial leading/trailing frames rejected; and
- bounded shift-and-sum period hypotheses in ARM-facing map space.

The host FFT accelerates exact integer correlation calculation.  It does not
freeze the internal scaling or rounding of a future RTL FFT.

## Frozen inputs

| Role | Capture/chunk | Samples | Compressed SHA-256 |
|---|---|---:|---|
| primary positive | `cap-20260831T071200-9184cf0ad6cc`, 15 MS/s chunk 0 | 4,194,304 | `68732179d9e147e0f173677f810e032d5240fc3ba024cb9045fe17dff9f38946` |
| independent weaker positive | `cap-20260831T044729-6a598698a226`, 15 MS/s chunk 278 | 3,145,728 | `fd6bc878e76d52671c5ea1c8f3ceae773e2539da285363c52118f698581bdaae` |
| independent RF negative | `cap-20260831T052807-77e01d5101ea`, 15 MS/s chunk 0 | 5,242,880 | `d33e16b72bb64a7718fbdc3063fcce7d92ea1d33cb3f3077ac78edc010cedb50` |

Each positive also has a deterministic frame-scrambled score control.  The
control preserves the score distribution and destroys repeated epoch; it is
not represented as independent RF evidence.

## Result and design choice

All values below use eight-bit normalized scores, a bounded `+/-10 ppm` period
bank in `3.125 ppm` steps, and the existing joint epoch gates of peak/median
`>=1.15` and robust z `>=6.0`.

| Input | Phase bin | Tile | Phase error | Peak/median | Robust z | Gate |
|---|---:|---:|---:|---:|---:|---|
| primary positive | 1 sample | 64 frames | 12 samples | 1.936 | 12.549 | pass |
| weaker positive | 1 sample | 64 frames | 1 sample | 1.550 | 6.205 | pass |
| RF negative | 1 sample | 64 frames | n/a | 1.283 | 4.561 | reject |

The weaker positive is the decisive geometry control.  At 64 frames its
two-, four-, five-, and eight-sample phase bins have robust z values `4.742`,
`5.217`, `5.357`, and `4.375`; all fail the unchanged z gate.  Coarse bins are
therefore rejected even though they make the primary positive appear stronger.

The selected acquisition-v1 candidate is:

- one sample per phase bin: 20,000 bins and the full 66.7 ns acquisition grid;
- eight-bit normalized scores;
- 64 frames per tile, or 85.333 ms;
- 16-bit stored map words, whose maximum is only `64 * 255 = 16,320`;
- 40,000 bytes per map and 468,750 bytes/s per template; and
- two templates, if searched concurrently, below 1 MB/s total map traffic.

At Zynq-7010 RAMB36 geometry a 20,000-deep, 18-bit physical implementation is
approximately ten blocks per map, or twenty for ping-pong maps.  This remains
an estimate until an out-of-context implementation report exists.

## Numerical and test evidence

- The maximum binary64 overlap-save distance from an integer correlation was
  `1.12e-8` LSB in the primary positive and below `7e-10` in the other inputs,
  far inside the oracle's `0.125`-LSB rejection boundary.
- Unit tests compare every score against the direct integer correlator and
  exercise starts immediately before, at, and after the 447-output FFT boundary.
- Tests cover exact normalized-score ties, partial-frame rejection, map
  overflow rejection, deterministic cadence drift, and noise-only rejection.
- The executable study tool has a bounded synthetic end-to-end CLI test.

Machine-readable results and their SHA-256 digests are:

- `starlink-pss-acquisition-oracle-v1.json`:
  `8165f8be6331911e2319dd9f98e56c99b6136c793241a7cd03757dba6ab13f00`;
- `starlink-pss-acquisition-oracle-v1-independent-positive.json`:
  `4a632a649b95a8f688b0777c4b4d2176e188631af7758dc73c477a3fcf4a8222`;
- `starlink-pss-acquisition-oracle-v1-independent-negative.json`:
  `13eaef1466bf74672751f3fbd6d435b6a8bd539544a75ced2f2cedfb46767505`.

## Boundaries and next gate

Three chunks do not freeze a production false-alarm policy.  The next offline
gate must run this exact configuration over the declared multi-capture positive
and negative partitions and account for the period-bank look-elsewhere effect.
Only after that gate should RTL implementation freeze its FFT scaling, score
normalizer, map BRAM layout, and tile ABI.
