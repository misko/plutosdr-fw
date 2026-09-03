# Starlink PSS 15 MS/s loss-aware PSMA 1.1 checkpoint

Status: **PASS OFFLINE / DO NOT MERGE / RADIO UNTOUCHED**

This checkpoint closes the source-only integrity boundary between one
non-backpressured RX stream, continuous acquisition, the atomic phase-map
snapshot, and bounded ARM map selection. It does not connect the path to the
RX shell, assign a system MMIO aperture, build a firmware image, contact a
radio, or establish frame alignment.

## Loss-detecting ingress

`starlink_pss_sample_cdc` accepts CI16 samples plus their 64-bit accepted-sample
index in the AD936x RX clock domain and transfers a 97-bit payload into the
100 MHz acquisition domain through a 128-entry Gray-pointer dual-clock FIFO.
It never backpressures RX or DMA. FIFO-full samples are counted with a
saturating counter, latch a sticky overflow flag, and cause the first later
accepted sample to carry an explicit gap. Independent reset synchronization
purges both pointer domains so stale payload cannot cross a reset epoch.

The functional tests pass at depth four and the production depth 128. They
prove ordered transfer, six deliberately injected drops, two independent reset
purges, and explicit gap recovery. The Vivado 2022.2 OOC gate for
`xc7z010clg400-1` uses a 16.270 ns source clock and 10.000 ns acquisition clock,
closes post-opt timing at setup WNS +2.025 ns and hold WHS +0.137 ns, reports
zero critical CDC paths, and emits all three Gray-bus skew constraints. It uses
148 LUTs, 242 registers, one RAMB36E1, and one RAMB18E1.

## Complete health epoch

`starlink_pss_acquisition_health` converts every event needed to decide whether
a map is trustworthy into saturating counters and sticky reset-epoch flags.
It covers ingress loss; scheduler gap, absolute-index error, and overflow;
aggregate detector-fault episodes; forward FFT, kernel join, product,
inverse-FFT, exponent, and candidate-path faults; score phase/index
discontinuity; and zero denominator. Current and maximum ingress and candidate
FIFO occupancy are also observable.

The reduced-width health test proves saturation, two detector-fault episodes
rather than level cycles, all twelve acquisition-core sticky causes, and reset
clearing. The production IQ-to-map OOC composition still closes its 100 MHz
post-opt gate at setup WNS +0.364 ns and hold WHS +0.011 ns. The health change
raises the composition to 8,079 LUTs and 12,463 registers while retaining 38.5
BRAM tiles and 32 DSP48E1s. These are OOC planning data; only a complete shell
route can decide whether the XC7Z010 image fits.

## PSMA 1.1 and ARM behavior

PSMA 1.1 preserves every ABI 1.0 register through `0x84` and appends ten health
words through `0xac`. The atomic CDC mailbox contains 24 full words, two 10-bit
candidate FIFO levels, and two ready bits: 790 source bits, 1,580 synchronizer
bits, and 790 destination bits. The isolated bridge passes all four asynchronous
clock simulations, the 10 MHz snapshot stress case, and exact 26-word snapshot
checking. Its complete 100/100 MHz routed OOC gate closes at setup WNS +2.520 ns
and hold WHS +0.019 ns with zero critical CDC rows, all three bus-skew constraints
met, 504 LUTs, 3,687 registers, and no BRAM or DSP.

The ARM parser accepts only exact version/capability pairs 1.0/`0x1f` and
1.1/`0x3f`. ABI 1.0 never reads beyond `0x84` and synthesizes zeros for absent
health fields. ABI 1.1 rejects unknown flags and nonzero reserved candidate-FIFO
bits. A copy remains owned by the FPGA unless its before/after identity,
generation, command status, and continuity-critical fault epochs are coherent.
Ingress drops, scheduler faults, detector faults, and phase discontinuities are
continuity failures; queue occupancy and zero-denominator telemetry remain
visible without falsely invalidating an otherwise coherent copy.

The bounded rerun passes strict native compilation, 32-bit ARM EABI cross
compilation, ASan/UBSan, two complete 20,000-word ABI paths, retained-bank
failure cases, and all 13 C/Python differential oracle cases. The frozen
functional summary records `radio_contacted=false`.

## Source and safety boundary

The coherent firmware source is commit
`3fa1b1ba3a3bd7f115231ae8ffb8983300259d8e`, tagged
`starlink-rx-only-dnm-v1-source/firmware-pss15-health-abi11-v1`. It pins HDL
commit `b7b564dd5e6a66a5c1ddf8f144d3bb6a9f8fc86a`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-health-abi11-v1`. The independently
tested ingress first appeared at HDL commit
`883e9824cebc2c8eaac0ad818cde22595dfd65e0`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-sample-cdc-v1`.

Firmware-main PR #96 changed only the append-only experimental-gitlink
denylist. All five checks passed and it merged as
`4e443ec0463c5814e39819c4162ac9e94276ff78` before the experimental parent
advanced its `hdl` gitlink. No experimental HDL, ARM acquisition source, parent
gitlink, firmware image, or PPU change was merged to main.

No IIO context, USB endpoint, network radio, serial console, DFU endpoint, or
flash was opened. The only reserved future RAM-validation target remains serial
`104000bac4950008230026001b440a003a`; all other radios remain unallocated.

The next gate is a complete one-RX shell integration and real placement/route.
It must preserve the existing RX DMA as a detector-independent tap, assign a
versioned AXI aperture, and prove clocks, resets, CDC, timing, resources, and
the absence of TX hierarchy before any RAM-only radio trial.
