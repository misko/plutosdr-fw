# FPGA tracker native-IIO completion record

Status: 60 MS/s native USB/Ethernet result transport and cabled fine timing
complete. Experimental firmware: **DO NOT MERGE INTO FIRMWARE MAIN**.

This append-only record supplements the historically sealed
`FPGA_tracker.md` and `FPGA_tracker_60MS.md` files. It does not alter or weaken
their 15/30/60 MS/s gate definitions.

Authorized receiver: `104000bac4950008230026001b440a003a` at topology `5-2`.

Cabled transmitter: `1040007c4a94000211000b009186843ef2` TX1 at topology
`3-11`, connected only through the declared exact 30 dB attenuator to receiver
RX1. Both radios were left in their persistent runtimes; no experimental image
was written to QSPI.

## Native transport result

The `starlink-pss-iio-v5-dnm` RAM image uses two dedicated IIO devices:

- `starlink-pss-map` exports each 20,000-bin coarse map as 200 zero-padded
  256-byte scans (`le:U32/32X64>>0`, 59 logical words);
- `starlink-pss-track` exports each 26-word fine result as one zero-padded
  128-byte scan (`le:U32/32X32>>0`).

At 60 MS/s, map start indexes remain in canonical 15 MS/s units. Adjacent maps
advance by 1,280,000 canonical samples, or 5,120,000 source samples. PPU
multiplies a coarse candidate index by four before scheduling the full-rate
tracker.

Fresh-epoch USB validation received three maps (600 chunks, 153,600 bytes) in
0.279 seconds and 16 fine packets (2,048 bytes) in 0.223 seconds. Generations,
start indexes, request IDs, and scheduled centers were continuous, and every
map/tracker validation, push, and hardware-fault field remained zero.

A fresh Ethernet context at `ip:192.168.1.17` received two maps (102,400 bytes)
in 0.187 seconds and eight fine packets (1,024 bytes) in 0.211 seconds with the
same continuity and zero-fault result. The initial connection immediately after
RAM boot timed out before the network was ready; a bounded retry after network
readiness passed.

The map device is one continuous acquisition session per FPGA reset epoch.
Stopping and reopening it can expose a delayed source-rate discontinuity and
latch hardware-health fault `0x40`; `acquisition_flush` cannot erase hardware
history. PPU now flushes before the first start, rejects a second session in the
same client, and rejects an epoch whose driver has already delivered a map.
Consumers keep one map buffer open across dwell/role boundaries. Fine streams
remain restartable.

## Fine-correlation defect and correction

The first native cabled run produced a strong coarse response but only about
`0.048` median normalized fine correlation. Its packet envelopes, coefficient
energy, scheduling, and period fit were valid, which localized the discrepancy
to coefficient values rather than transport.

The generator/C-tool memory format encodes I in bits `31:16` and Q in `15:0`.
The FPGA coefficient register accepts I in `15:0` and Q in `31:16`. The initial
PPU file loader preserved the file word and therefore interchanged I/Q at the
FPGA. Energy is invariant under that swap, explaining why structural checks
could not detect it.

PPU main commit `7fa26455417f52cadd4d1968147dbd47d1e64383` corrects the
conversion and adds:

- byte-exact coefficient-layout regression coverage;
- expected-serial binding for USB and Ethernet PSS contexts;
- the qualified C-equivalent three-map drift/robust analyzer;
- explicit canonical and source-rate candidate/period fields;
- fail-closed one-session coarse-map behavior; and
- correct propagation of operation `OSError` values through the shared radio
  lock.

PPU passed Ruff, strict mypy for all 74 source files, and 1,449 tests with 11
explicit hardware/browser skips. The commit is pushed to `origin/main`.

## Corrected cabled timing proof

The guarded runner at firmware DNM commit `5fa73e9b1` used one continuous map
session: three muted maps, three transition maps after TX start, and three
positive maps. It then ran positive A, a phase-continuous minimum-gain control,
and positive B using restartable fine streams.

The positive coarse maps measured peak-to-median `3.7084` and robust-z `59.51`,
compared with muted `1.3411` and `4.79`.

| Role | Results | Fitted period (source samples) | Worst residual | Median normalized score | Winner lag |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive A | 128 | 80,000.087733 | 0.5157 sample / 8.59 ns | 0.43432 | 13..25 |
| Minimum-gain control | 64 | not qualified | 129.2827 samples | 0.02079 | -118..120 |
| Positive B | 128 | 80,000.088030 | 0.4988 sample / 8.31 ns | 0.43445 | 13..24 |

Both positive scores exceeded the muted-control median by more than 20 times.
Both fitted periods were within one source sample of 80,000; both positive
worst-case residuals were within one source sample; neither positive run hit
the search-aperture edge. All map/tracker/push/validation fault gates passed.

Cleanup restored `.17` to 30.72 MS/s and 18 MHz bandwidth. `.18` was verified
at `-89.75 dB`, with TX LO powered down, all DDS amplitudes zero, zero-source
selectors selected, and its cyclic buffer released. Final PPU recovery proved
USB departure/return, route release, persistent AD9361 1R1T identity, firmware
`v0.48-plutoplus-spf-iq-direct-async-v3`, and unchanged QSPI SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`.

This proves synthetic cabled 60 MS/s PSS timing and result transport. It does
not claim 60 MHz analog bandwidth, live Starlink reception, SSS, or frame lock.

## Evidence identities

- v5 DFU:
  `7c5f5c3b8307cc49fadbe416da5f19ceb86350c0ddd9e6bd15f98cd423dd1038`
- USB maps:
  `361e72dce0dff393019dad41235bd1a0bc506ab6003a56ac257f5bb2d1f6874e`
- USB fine packets:
  `baa38f3562b3e1910f3ad41ecd65d22926b89ad7263e0cd5ad12eb87479e5e10`
- Ethernet maps plus fine packets:
  `da8e55c166d835e2020a871c5b898c5fdffc5373b549fad697a2a43f0bb03cd8`
- corrected cabled run:
  `4b9243e62b5349b99cb9d36637e13a9d6528cef8a67f0cd63f595d62d3f4795c`
- final RAM deployment:
  `0d0b63019574808e293612d8621ff4d895b96d7243da4cfdc9575987893618ef`
- final recovery:
  `ea43484679438c71e4d3313195ac0f4fe3344f7585d57396b6cb476342fa1ee6`
- guarded runner source:
  `7ffb253e20a4b0526bf4016a149c4f8df11ebffd9d4cdb97bc011d97894d636f`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/iio-v5-20260907`

## Next gates

1. Complete M6 by running the parameterized sparse tracker at 30 MS/s through
   the same positive/control/positive cabled test and proving at-most-one
   30 MS/s source-sample timing error.
2. When the LNB is available, run M4/M9 as bounded on-channel, off-channel, and
   repeated on-channel roles over Ethernet. Keep one map stream open for the
   complete reset epoch and record every candidate, miss, and health counter.
3. Use the live coarse timing to test a small frequency-compensated coefficient
   bank, then add cadence lock. Do not add SSS until PSS timing and CFO are
   repeatable on live captures.
4. Add SSS hypotheses and joint PSS/SSS consistency as a new gate, then define
   final frame-lock acquisition/loss hysteresis. No earlier result is promoted
   retroactively to frame lock.
