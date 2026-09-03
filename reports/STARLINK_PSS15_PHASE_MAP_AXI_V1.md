# Starlink PSS 15 MS/s phase-map AXI/CDC checkpoint v1

Status: **PASS OFFLINE / DO NOT MERGE / RADIO UNTOUCHED**

This checkpoint adds the bounded processor boundary after the continuous
15 MS/s IQ-to-phase-map path. It does not connect the detector to the RX shell,
run ARM candidate selection, establish frame lock, build a firmware image, or
qualify a radio.

## Implemented boundary

The bridge presents a single AXI4-Lite register bank to software while keeping
the acquisition clock independent from the AXI clock. It transfers map reads,
bank releases, flushes, enable state, and one atomic telemetry snapshot with
explicit CDC protocols. The acquisition side retains ownership of both map
banks until software releases one; no command can backpressure samples or
normalized scores.

The AXI front end is deliberately single-outstanding and has no short injected
peripheral timeout. AW and W may arrive independently, write strobes are
honored, and B/R responses remain stable under backpressure. A `MAP_DATA` read
waits for the map-domain acknowledgement, returns one zero-extended word, and
increments the selected phase without wrapping. A concurrent software retarget
is preserved rather than overwritten by the returning auto-increment. A local
map reset aborts an in-flight data request with a bounded zero response while
leaving AXI transport reset under `s_axi_aresetn` alone.

The telemetry mailbox transports 15 32-bit words plus two ready bits: 482
source bits, 964 synchronizer bits, and 482 destination bits. Software receives
a level interrupt while either synchronized ready bit is set. The documented
sequence is identify, enable, snapshot, select a ready bank, copy exactly
20,000 words, run bounded ARM extraction, then release the bank.

At the production geometry this is a 40,000-byte immutable map every 64 frames,
or about 468.75 kB/s at 750 Hz, rather than a continuous 60 MB/s CI16 stream.

## Functional verification

Icarus Verilog 12.0 passes a structural gate, four integrated bridge-plus-real-
map clock cases, and a deliberately slow 10 MHz map-clock snapshot stress test.
The integrated cases cover approximately 71.4, 62.5, 100, and 125 MHz map
clocks against 100 MHz AXI. Across them, the longest legal map read takes 18 AXI
cycles, demonstrating why the earlier short-timeout helper was unsuitable.

Each integrated case performs 11 map reads, two atomic snapshots, both split
AW/W arrival orders, one concurrent `MAP_DATA` read and `MAP_INDEX` write,
read-response backpressure, map-reset abort, invalid read and release commands,
and flush. The snapshot stress test checks all 16 visible words across two
coherent generations and one pending-request overrun. Exact results are frozen
in `reports/starlink-pss15-phase-map-axi-v1-simulation-summary.txt`.

## Routed physical gate

Vivado 2022.2 synthesized, placed, and routed the isolated bridge for
`xc7z010clg400-1` with both clocks constrained to 100 MHz:

| Check | Result |
|---|---:|
| Setup WNS | +2.648 ns |
| Hold WHS | +0.037 ns |
| LUT | 398 |
| Registers | 2,455 |
| RAMB36E1 / RAMB18E1 | 0 / 0 |
| DSP48E1 | 0 |
| Methodology violations | 0 |
| Critical CDC rows | 0 |
| Bundled-data bus-skew constraints met | 3 of 3 |

The gate also requires the exact known CDC classes, zero unexpected
`check_timing` categories apart from the explicitly false-pathed asynchronous
AXI reset, and complete 482/964/482-bit snapshot storage. Its OOC boundary uses
registered synthetic input delays; full-system integration must replace those
with real shell timing and rerun placement, routing, CDC, and skew analysis.
The bridge figures exclude the already accounted phase-map RAM and the
correlator datapath.

## Source and safety boundary

The HDL is frozen at commit
`e2e1b87fccfb7efbeb3612e2a3b5a0fea919ba93`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-phase-map-axi-v1` on
`codex/starlink-rx-only-do-not-merge`. Firmware-main guard PR #95 appends this
exact component pin to the base-owned denylist before the experimental parent
advances its gitlink; all five checks passed and it merged as
`d2fcc1175dbf0c866288b0c369cc2cfb314979ba`. This checkpoint contains no PPU
change.

No IIO context, USB device, network radio, serial console, DFU endpoint, or
flash was opened. The only reserved future RAM-validation target is serial
`104000bac4950008230026001b440a003a`; all other local radios remain free.

The next checkpoint is ARM-side bounded candidate extraction and explicit
`ACQUIRE -> CONFIRM -> LOCK -> TRACK -> HOLDOVER -> ACQUIRE` semantics using
immutable maps. Thresholds remain evidence-driven, and neither a single peak
nor this transport checkpoint is called frame lock.
