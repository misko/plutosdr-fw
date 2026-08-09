# Gain-series v4 RC6 DAC-clock-qualified FIFO reset candidate

RC6 is an unpromoted, RAM-boot-only candidate. It retains the RC2 protocol-v3
RX gain-series metadata, coherent RX sample counter, direct USB, and direct IP
support. It changes only the initial state and regression coverage of the TX
timestamp FIFO reset synchronizer introduced in RC4/RC5.

## RC5 hardware result

RC5 passed source, RTL, routed CDC, routed timing, packaging, checksum, and
provenance gates. Its first two-radio volatile boot passed the cabled TX2
loopback test. Its second volatile boot left one radio at approximately
`-104/-111 dBFS` on RX1/RX2, reproducing the original boot-dependent FPGA TX
starvation. RC5 was restored to production and rejected before downstream
candidate USB/IP/Zarr gates.

## Root-cause hypothesis and change

The TX XPM async FIFO is written by `dma_clk` and read by `dac_clk`. RC5
registered the DAC reset in `dac_clk`, synchronized it to `dma_clk`, and held
the FIFO reset for five write-clock cycles. However, that source-domain reset
register initialized deasserted. If `dma_clk` started before `dac_clk`, the
write-domain hold counter could expire before the read domain had observed any
clock. Whether that happened depended on boot clock ordering, matching the
observed one-boot-pass/one-boot-fail behavior.

RC6 initializes the DAC-domain reset register asserted. The FIFO therefore
cannot leave reset until `dac_clk` has actually toggled and sampled the
deasserted DAC reset; only then can the registered level cross into `dma_clk`
and begin the five-cycle release hold.

The FIFO reset testbench now deliberately runs ten DMA/write-clock cycles with
the DAC/source clock stopped. It requires reset to remain asserted throughout,
then starts the DAC clock and requires a bounded synchronous release. This is
the boot ordering RC5 did not test.

## Required gate

Do not write RC6 to QSPI. Require clean source, RTL, routed CDC, bus-skew, and
timing gates. Then require at least three independent volatile RAM boots on two
radios, with the TX2 cabled tone visible on RX1 and RX2 in every epoch and TX
muted on every exit path. Only after all repeated TX boots pass may the
protocol-v2 compatibility, protocol-v3 USB and simultaneous receive,
direct-IP parity, and 100-frame-per-radio V7 Zarr gates run. Promotion remains
a separate decision.
