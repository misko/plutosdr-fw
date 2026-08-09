# Gain-series v4 RC3 FPGA bisection candidate

RC3 is an unpromoted, RAM-boot-only hardware-test candidate. It keeps the RC2
gain-series RX counter, metadata, direct-USB, and direct-IP work, while reverting
the only RC2 HDL change in the TX timestamp datapath.

## Why this candidate exists

Two-radio RC2 testing found:

- all RX protocol-v2 and protocol-v3 gates passed;
- direct USB and direct IP passed;
- 100 frames per radio at 2^19 samples per channel round-tripped through Zarr;
- the cabled TX2-to-RX1/RX2 tone intermittently disappeared after an RC2 FPGA
  boot, with the affected physical radio changing between boots;
- RC2 userspace with the production FPGA passed TX on both radios;
- production userspace with the RC2 FPGA reproduced the one-radio TX failure.

The routed RC2 design met all declared timing constraints. The evidence therefore
isolates the regression to the RC2 FPGA image or its power-up state, rather than
the USB/IP gadget software. RC3 reverts the TX timestamp Gray-code source register
added by HDL commit `e663136`, but retains the RX closed-loop sample-counter CDC.

## Acceptance gate

Do not write RC3 to QSPI. RAM boot the exact CI artifact on two radios and require:

1. Three cold/RAM-boot epochs per radio.
2. A TX2 tone visible on both RX1 and RX2 in every epoch.
3. TX muted in a `finally` path after every test.
4. Protocol-v2 compatibility and protocol-v3 USB receive passes.
5. Simultaneous two-radio protocol-v3 receive passes.
6. Direct-IP protocol-v3 receive passes.
7. A 100-frame-per-radio V7 Zarr round trip passes.

If TX still fails, retain RC2/RC3 as unpromoted and implement an explicit,
clock-domain-safe reset sequence for the TX asynchronous FIFO as the next
candidate. Promotion requires a separate reviewed release and production pin
update after all hardware gates pass.
