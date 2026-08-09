# Gain-series v4 RC5 registered-reset CDC candidate

RC5 is an unpromoted, RAM-boot-only candidate. It retains the RC2 protocol-v3
RX gain-series metadata, coherent RX sample counter, direct USB, and direct IP
support. It refines only the deterministic FPGA TX FIFO reset added in RC4.

## Evidence and change

RC4 connected the previously inactive XPM async-FIFO reset and restored the
registered Gray-code timestamp crossing. Its RTL reset simulation passed, but
Vivado's routed CDC gate rejected the image for a CDC-10
combinational-before-synchronizer path. No RC4 deployment artifact was
published and RC4 was never loaded on hardware.

The DAC reset input is synchronous to `dac_clk`, while the FIFO reset must be
synchronous to `dma_clk`. RC4 fed that source reset directly into the DMA-domain
two-flop synchronizer. RC5 first registers the reset in `dac_clk`, then crosses
the registered level into `dma_clk`, where the startup/runtime hold counter
drives the FIFO reset. This gives both sides of the crossing explicit clocked
boundaries and preserves the minimum four-cycle FIFO reset hold.

Failed Kalman builds now upload routed CDC and timing diagnostics so any future
post-route rejection identifies the exact path without another diagnostic
build.

## Required gate

Do not write RC5 to QSPI. Require a clean routed CDC report with no CDC-10 paths
and all declared timing gates passing. Then require three independent volatile
RAM boots on two radios, with the TX2 cabled tone visible on RX1 and RX2 in every
epoch and TX muted on every exit path. Only then run protocol-v2 compatibility,
protocol-v3 USB and simultaneous receive, direct-IP parity, and the 100-frame
per-radio V7 Zarr round trip. Promotion remains a separate decision.
