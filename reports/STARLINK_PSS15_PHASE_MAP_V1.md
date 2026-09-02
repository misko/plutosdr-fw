# Starlink PSS15 continuous phase-map RTL checkpoint

Status: **isolated RTL pass; not an FFT, detector, integrated image, or radio
qualification**.

This checkpoint implements the first continuous-acquisition FPGA slice selected
by `starlink-pss-acquisition-oracle-v1`. It consumes an already normalized
eight-bit score at every canonical 15 MS/s candidate start. It does not yet
generate those scores from IQ samples.

## Implemented contract

- 20,000 one-sample phase bins, matching the 750 Hz frame period at 15 MS/s;
- exact accumulation of 64 complete nominal frames into 16-bit words;
- two immutable published banks, allowing one map to be read while the other
  is filled;
- consecutive phase and absolute-score-index checks;
- explicit partial-map invalidation and clearing on a gap, mismatch, reset, or
  disable during accumulation;
- publication of a tile already complete when disable arrives in its drain
  cycle;
- fail-closed read/release behavior, including same-cycle read plus release;
- saturating diagnostic counters; and
- no backpressure output and no connection to the existing RX DMA path.

The 20,000-word non-power-of-two memory is explicitly divided into ten
2,048-word simple-dual-port segments per bank. This prevents synthesis from
allocating the unreachable tail of a 32,768-word inferred memory.

## Deterministic simulation

Run from `hdl/library/starlink_pss_acquisition`:

```sh
./run_tests.sh
```

The test uses reduced geometry so it can exhaustively read both banks. It
checks two back-to-back tiles with no idle score at the bank boundary, exact
sums and metadata, gap abort and clear, valid and invalid lifecycle requests,
same-cycle read/release rejection, a host read of one published bank while the
other bank is actively filling, disable-at-drain publication, and score
accounting. The frozen result is:

```text
PHASE_MAP_PASS bins=8 frames=4 ping_pong=1 complete_only=1 gap_abort=1 fail_closed_read=1 accepted=139 discarded=3
```

## Vivado 2022.2 OOC gate

Run from the same directory with a fresh absolute output directory:

```sh
./run_phase_map_ooc.sh /absolute/output/directory
```

For `xc7z010clg400-1` at 100 MHz, post-optimization and before placement, the
source-locked gate reports:

| LUT | FF | RAMB36E1 | RAMB18E1 | DSP48E1 | Setup WNS | Hold WHS |
|---:|---:|---:|---:|---:|---:|---:|
| 542 | 722 | 20 | 0 | 0 | +1.190 ns | +0.204 ns |

The run has zero methodology violations and zero nonempty `check_timing`
categories. The OOC input constraint assumes a synchronous 0.5--1.0 ns source
arrival window. Full-shell timing must replace that boundary assumption with
the actual upstream register paths.

## Source and limits

Reviewed HDL source commit:
`d291871923c6dc6cc2f30745d2e9d8a6abd3188f`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-phase-map-v3` on the experimental
do-not-merge branch. The immutable v1 source tag is deliberately superseded:
review found that its two memory banks shared a read-address mux, so a host read
could select the active fill address. V2 corrected that mux. Subsequent
lifecycle review found that disable in `WAIT_FRAME` or `DRAIN` could reserve and
strand the next clean bank; v3 returns or preserves the bank and tests
disable/re-enable through both states. V1 and v2 were never integrated into the
parent source graph, built into an image, or used on a radio.

This checkpoint does **not** implement IQ buffering, overlap-save FFT/IFFT,
template multiplication, energy normalization, score quantization, period-bank
search, winner reduction, AXI control, CDC, or shell integration. Consequently
it does not establish PSS timing, live recurrence, Starlink identity, SSS, or
30/60 MS/s operation. No radio was contacted and no image was built or flashed.
