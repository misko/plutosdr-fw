# Gain-series v4 RC7a TX pipeline diagnostic candidate

RC7a is an unpromoted, RAM-boot-only diagnostic candidate. It preserves the
RC6 data path and adds sticky, read-only observations at every boundary of the
FPGA TX timestamp wrapper. It does not claim to fix the remaining intermittent
TX starvation.

## Evidence leading to RC7a

RC6 failed its first two-radio volatile-boot TX gate. Radio
`104000bac4950008230026001b440a003a` returned approximately `-104/-122 dBFS`,
negative tone SNR, and coherence `0.218`. On the same FPGA image and same boot,
radio `1040007c4a94000211000b009186843ef2` passed with coherence greater than
`0.999999`. Both radios exposed identical AXI AD9361 TX status, including the
underflow bit; timestamp insertion was disabled and the discard count was zero.

This rejects RC6's DAC-clock-qualified FIFO-reset hypothesis and places the
missing evidence inside the timestamp wrapper, between DAC DMA and `util_upack2`.

## Diagnostic interface

DAC GPIO output bit 0, previously unused, selects a diagnostic page in DAC GPIO
input register `0xB8`. The normal timestamp interval continues to use GPIO
output bits 31:1, and bit 0 does not alter TX samples, resets, or flow control.
When bit 0 is clear, `0xB8` remains the existing 32-bit timestamp discard count.
When bit 0 is set, `0xB8` contains:

- bits 31:24: sticky DMA-side activity (transfer request, valid, ready, FIFO
  write, full, reset busy, write possible, reset released);
- bits 23:16: synchronized sticky DAC-side activity (downstream ready, FIFO
  read, downstream valid, nonempty, reset busy, read possible, transfer-start
  tag, upack reset released);
- bits 15:0: low 16 bits of the timestamp discard count.

The host test reads the page only after preserving the ordinary registers and
restores the prior GPIO output value in a `finally` path. Each sticky bit is
monotonic after FPGA configuration, making independent DAC-to-DMA
synchronization safe.

## Required use

Do not write RC7a to QSPI. First require clean source-graph, RTL, routed CDC,
bus-skew, timing, packaging, checksum, and attestation gates. Then RAM boot both
radios and run the TX2 loopback gate. If a radio fails RF quality, preserve its
partial JSON report: the first false sticky boundary identifies the next
evidence-based repair. Restore production firmware and mute both transmitters
on every exit path.
