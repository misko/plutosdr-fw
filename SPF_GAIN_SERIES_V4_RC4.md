# Gain-series v4 RC4 deterministic TX FIFO reset candidate

RC4 is an unpromoted, RAM-boot-only candidate. It retains the RC2 protocol-v3
RX gain-series metadata, coherent RX sample counter, direct USB, and direct IP
support. It changes only the FPGA TX timestamp FIFO reset behavior.

## Evidence and change

Hybrid FIT bisection showed that the cabled TX2 tone passes with RC2 userspace
and the production FPGA, but can disappear on one radio after any boot using
the RC2 FPGA. The affected physical radio can change between boots and remains
consistent within one boot. This isolates the failure to FPGA power-up state.

RC3 attempted to revert the TX timestamp Gray-code source register. The image
built, but the post-route CDC gate correctly rejected that design for CDC-10
combinational-before-synchronizer paths. RC3 was never tested on hardware.

RC4 restores the registered Gray-code crossing and connects the previously
inactive XPM async-FIFO reset. The reset is synchronized into the FIFO write
clock domain, asserted deterministically at FPGA configuration, held for at
least four complete write-clock cycles, and reasserted after DAC reset.

## Required gate

Do not write RC4 to QSPI. First require three independent volatile RAM boots on
two radios, with the TX2 cabled tone visible on RX1 and RX2 in every epoch and
TX muted on every exit path. Only then run protocol-v2 compatibility,
protocol-v3 USB and simultaneous receive, direct-IP parity, and the 100-frame
per-radio V7 Zarr round trip. Promotion remains a separate decision.
