# Gain-series v4 RC7b timing-isolated TX diagnostics candidate

RC7b is an unpromoted, RAM-boot-only diagnostic candidate. It preserves RC7a's
sticky TX pipeline observations while isolating them from the timing-critical
DMA ready path.

## RC7a build RCA

RC7a passed source-graph checks and all focused RTL simulations, synthesized,
routed, and generated a bitstream. It was rejected before packaging because
the routed design missed setup timing:

- WNS: `-0.203 ns`
- TNS: `-1.337 ns`
- failing endpoints: 12, all on the 100 MHz `clk_fpga_0` domain
- worst source: DAC DMA store-and-forward BRAM output
- worst destination: DAC DMA `dest_beat_counter`

The worst path showed Vivado had absorbed the 64-bit timestamp comparison from
`s_axis_ready` into the new diagnostic hierarchy. RC6 passed timing with only
about `+0.010 ns` margin, so that placement perturbation was sufficient to
reject the candidate. The archived routed timing report is authoritative; this
was not a Verilog syntax, block-design, CDC, or hardware failure.

## RC7b change

The diagnostics no longer tap `s_axis_ready` directly. That bit was redundant:
the combination of upstream-valid, FIFO reset/full/possible, and actual FIFO
write evidence distinguishes the same failure cases. Its position now records
whether timestamping was ever enabled, which also detects an unexpected
runtime configuration. The `tx_pipeline_debug` instance carries a
`KEEP_HIERARCHY` attribute so synthesis cannot absorb the ready comparator into
the observation block again.

All other RC7a diagnostic bits and the normal timestamp-discard readback remain
unchanged.

## Required gate

First require positive routed WNS/WHS and passing CDC/bus-skew reports. Then RAM
boot both radios and run repeated TX2 loopback epochs. Never write RC7b to QSPI.
On RF failure, retain the partial JSON diagnostics, restore production firmware,
and mute TX on every exit path.
