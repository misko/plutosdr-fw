# Gain-series v4 RC9 registered timestamp-check candidate

RC9 is an unpromoted, RAM-boot-only candidate. It retains RC8's functional
fix for the false disabled-timestamp discard count and removes the timing path
that prevented RC8 from producing a deployable image.

## RC8 build failure and RCA

RC8 passed source verification and all four focused HDL simulations, including
the new disabled-timestamp regression. Vivado completed synthesis, placement,
and routing, but the clean build failed its mandatory timing gate:

- setup WNS: `-0.348 ns`;
- setup TNS: `-1.064 ns` across six endpoints;
- hold WHS: `+0.013 ns`.

The worst setup path ran from the TX DMA block RAM, through the 64-bit
timestamp range comparison and its shared carry chain, into the DMA `ready`
path. The comparison was therefore combinationally coupled to the upstream
DMA handshake. RC7b happened to route this logic with positive slack, but the
RC8 functional change altered optimization and exposed the latent path. A new
implementation seed would not constitute a robust fix.

## RC9 change

RC9 evaluates each timestamp word into registered `valid` and `discard`
decisions before allowing that word to handshake. AXI-stream requires the
producer to hold its data stable while `valid` is asserted and `ready` is
deasserted, so the behavior is protocol-correct. It adds one 100 MHz DMA clock
cycle only to timestamp words; timestamp-disabled IQ remains a transparent,
zero-added-stall path.

The discard counter now increments from the registered decision at the
timestamp handshake. This also removes the comparison-plus-counter carry chain
from a single cycle and counts each rejected timestamp exactly once.

The new focused simulation proves:

- a timestamp word is stalled for its one evaluation cycle;
- a valid timestamp is accepted without incrementing the counter;
- an invalid timestamp is accepted and counted exactly once; and
- disabling timestamping restores immediate IQ readiness without changing the
  counter.

The prior disabled-timestamp, FIFO-reset, TX-diagnostic, and counter-CDC tests
remain mandatory. RC9 must achieve positive routed setup and hold slack before
it may be RAM-booted.

## Hardware promotion gate

If the offline build passes, RAM-boot RC9 on both attached radios. Never write
this candidate to QSPI. The first hardware gate is cyclic DMA TX through
AD9361 internal loopback: the tone must be correct, every DMA/DAC pipeline bit
must assert, protocol-v3 metadata must validate, and the timestamp discard
count must remain zero. Then run protocol-v2 compatibility, simultaneous
protocol-v3 direct USB, 100-frame-per-radio V7 Zarr, direct-IP parity, and the
attenuated external TX2 loopback campaign across independent RAM boots.
