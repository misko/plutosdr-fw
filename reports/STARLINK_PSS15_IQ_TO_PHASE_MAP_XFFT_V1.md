# Starlink PSS 15 MS/s generated-XFFT IQ-to-phase-map checkpoint v1

Status: **PASS OFFLINE / DO NOT MERGE / NOT ROUTED / RADIO UNTOUCHED**

This checkpoint closes the source-only 15 MS/s path from continuous CI16
accepted samples to a bounded, immutable phase-map data product. It does not
connect the detector to the real RX shell, cross an AXI/CDC boundary, select a
robust peak on ARM, establish PSS frame lock, build firmware, or qualify a
radio.

## Implemented path

`starlink_pss_iq_to_phase_map.v` composes the already qualified overlap-save
score engine, a new event-driven phase tagger, and the existing ping-pong map:

1. Every accepted CI16 sample fans out to the 512-point overlap scheduler and
   exact 66-sample energy cache without RX backpressure.
2. Two actual regenerated XFFT v9.1 cores, the hash-locked upper-edge kernel,
   Q1.23 product, overlap qualifier, indexed energy join, and exact two-lane
   normalizer produce 447 eight-bit timing scores per block.
3. The phase tagger establishes phase zero at the first good score and advances
   modulo the configured frame length only on a valid score event. Wall-clock
   gaps with no valid score do not move phase.
4. A nonconsecutive absolute score index is suppressed and reported as a
   discontinuity. The bad index becomes only a continuity anchor; its following
   consecutive score restarts at phase zero.
5. A one-cycle, one-score-per-clock register boundary separates the tagger's
   64-bit continuity comparison from the map's independent phase/index checks
   and segmented BRAM enables.
6. The default map accumulates 20,000 one-sample phases over exactly 64
   consecutive frames into a 16-bit bank. Only a complete bank becomes
   readable; the second bank can fill while software reads the first.

The phase-zero origin is intentionally arbitrary after a restart. The peak in
the completed map supplies the candidate offset from that origin. Software
still has to apply the frozen robust peak, cadence, ambiguity, and confirmation
policy before declaring frame alignment.

## Deterministic generated-core replay

The same frozen 1,406-sample CI16 vectors used by the preceding IQ-to-score
checkpoint are replayed through both actual Vivado 2022.2 XFFT behavioral
instances and the new composition. Reduced map geometry uses 447 phase bins and
three frames, allowing all 1,341 exact scores to publish one complete map. The
test then reads every phase and checks it against the independent sum
`score[p] + score[p+447] + score[p+894]`.

The passing result is:

```text
IQ_TO_PHASE_MAP_XFFT_PASS samples=1406 scores=1341 phases=447 frames=3 exact_map_reads=447 map_peak_phase=0 map_peak_value=264 bounded_handoff_bytes=894
```

All map error and abort counters remain zero; publication count is one and the
accepted-score count is 1,341. Score indexes and phases are checked on every
score, and every map word is checked exactly. The separate phase-tagger test covers modulo wrap,
valid-time gaps, index-jump suppression and rebase, explicit discontinuity,
disable, and flush. The complete acquisition directory now passes 17 ordinary
RTL simulations.

The frozen vector evidence remains
`reports/starlink-pss15-iq-to-score-xfft-vectors-v1.json`, SHA-256
`6eaf98f478b1222042aca89e76828984f6bde6e486f0eacc06b5067f3b5d296d`.
The new simulation summary is
`reports/starlink-pss15-iq-to-phase-map-xfft-simulation-summary.txt`, SHA-256
`9c819b7128f60bf19ae623741d4a0cd0008ce0f4d7ab989f4ba81d3da2cfda24`.

## Default-geometry synthesis gate

Vivado 2022.2 regenerated the same two 512-point, signed 24-bit,
block-floating, convergent-rounding, natural-order, radix-4-burst XFFT cores.
The gate synthesized the full 20,000-bin, 64-frame composition for
`xc7z010clg400-1` and ran post-synthesis optimization at 100 MHz:

| Resource/check | Result | Device use |
|---|---:|---:|
| LUT | 8,018 | 45.6% |
| Registers | 12,290 | 34.9% |
| RAMB36E1 / RAMB18E1 | 26 / 25 | 38.5 tiles, 64.2% |
| DSP48E1 | 32 | 40.0% |
| Setup WNS | +0.364 ns | pass |
| Hold WHS | +0.011 ns | pass |
| Methodology violations | 0 | pass |
| Nonzero `check_timing` categories | 0 | pass |

Timing closure required three intentional boundaries. Registered lifecycle
state removed external reset/flush controls from the detector-wide ready chain;
the inverse-XFFT output now consumes continuously and fails closed if the
burst-sized candidate path cannot accept; and the score-to-map register
separates the two absolute-index comparisons. None reduces the
one-score-per-clock internal throughput. The measured candidate FIFO peak
remains 345 of 512.

The frozen OOC summary is
`reports/starlink-pss15-iq-to-phase-map-xfft-ooc-summary.txt`, SHA-256
`92af1c40a05c64cf5181d0f66492cd1b3da45654c6bc7b6953d3f8738a48dd9d`.
This is an optimized but unplaced OOC result. Its small hold margin and absence
of the RX shell make complete placement and routing mandatory.

## Bounded processor handoff

At the production geometry, one map is 20,000 16-bit words, or 40,000 bytes.
Sixty-four 750 Hz frames take 85.333 ms, so the sustained one-template handoff
is about 468.75 kB/s. This replaces the 60 MB/s continuous CI16 stream that a
15 MS/s host-side correlator would otherwise need. ARM can therefore apply the
more changeable robust peak/cadence policy to immutable maps without carrying
raw samples across the processor boundary.

## Source boundary and next gate

The HDL source is locked at commit
`c85a88109ef68020c5d318e045b7ad91660a8960`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-iq-to-phase-map-v2` on the
experimental `codex/starlink-rx-only-do-not-merge` branch. The retained v1
commit `af16286da82584421a1230c46aa70ed2db9dac7f` is superseded because it
changed the already checkpointed shared FIFO to cut a composed timing path.
V2 restores that FIFO byte-for-byte and moves the fail-closed boundary into the
IQ composition. Firmware-main guard PR #94 protects both immutable gitlinks
before the experimental parent advances; its merge commit is
`f0161837c11c39acb81fa7c45a3714d2dd4d2321`.

No IIO context, USB device, network radio, serial console, DFU endpoint, or
flash was opened. The only reserved future qualification target remains serial
`104000bac4950008230026001b440a003a`; every other local radio remains free.

The next 15 MS/s source gate is an explicit AXI/CDC/control boundary plus ARM
map acquisition and frozen candidate-selection replay. That is followed by the
actual one-RX sample tap and a complete route. Only after deterministic shell
replay and RAM-only exact-radio qualification should the rate ladder introduce
the independently qualified 30 MS/s x2 frontend, followed later by 60 MS/s x4.
