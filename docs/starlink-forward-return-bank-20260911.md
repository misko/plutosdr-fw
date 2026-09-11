# Whole forward-return bank — component and actual observer, DO NOT MERGE

Native 60 MS/s fine search and the independent 2.5 MS/s CI16 IIO inspection
stream remain requirements. This is a storage/control component for separating
real-time FFT capture from later kernel/product replay, NOT a new deployed
receiver. All 22 current receiver runtime modules remain byte-identical to the
scalar-fault reference. The generated FFT campaigns use an additive observer;
no observer output drives the reference DUT.

## Ownership and interface

Reserve the whole 512x36 bank before starting the real-time FFT. Capture
ordinal, LAST, exponent and descriptor checks are local. Downstream READY is
not used for capture capacity. A separate same-epoch qualified seal is required
after full capture (or on the final capture edge) before any replay is valid.
Local framing alone cannot seal. A synchronous RAM reader holds data under
stall and emits one word per clock when unstalled. Only final consumption
returns ownership. Reservation offers while busy cannot alter held metadata.

The caller must retain input/vendor/status/final-fence validation, immediate
public fault vetoes, a bounded job watchdog and common reset. The bank does not
provide CDC, publication authorization, expiry/watchdog, a second payload bank
or RF timing accuracy. Payload RAM is not reset; only complete fresh capture
plus qualification can make it reachable. Abort or malformed input immediately
fences replay and latches quarantine until reset. No late stale RAM is exposed.

## Functional evidence

31 component/source tests and 11 observer-evidence tests are included in the
1077-test regression, all passing (116.92 s). Component campaign: 12 blocks,
6144 words, 3108 stalled-valid clocks, 16786 total clocks; three reset boundaries
and full-rate/gapped capture, early/delayed seal and held final replay. Twenty
fault cases include ordinal, LAST, metadata, exponent, extra/orphan words,
early/duplicate/unknown seal, unknown control values and abort during capture,
waiting, replay and held final. Each requires immediate fencing, sticky
quarantine and 512 fresh recovery words. Nine unsafe mutations are rejected.

Initial component tests exposed a 120-bit testbench hold snapshot for a 121-bit
tuple, then a missing internal read-bound assertion. Those bench issues were
corrected; the bank RTL itself did not change. Failed XML/logs and the initial
bench are retained. The extra-read mutant was externally masked on final
retirement but violated the intended bounded RAM-read contract; its rejection
now explicitly checks that internal contract, not a fabricated output error.

The first observer was inserted before the bench clock declaration, creating
an implicit wire and causing both campaigns to hit the absolute deadline with
no result. The corrected observer follows declarations, and changes its sink
READY only on the falling edge to avoid a sampling race. Original stimulus and
all 22 runtime modules are unchanged. Failed prepared sources/logs remain saved.

Corrected actual generated FFT runs pass:

| Observer | Completed blocks | Checked words | Reservations | Seals | Stall clocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main | 71 | 37689 | 109 | 98 | 15077 |
| Auxiliary | 73 | 37455 | 92 | 81 | 15008 |

Partial prefixes from later cancelled jobs are included in the checked-word
counts. They are private replay, not public detector results. All 64512 original
seven-stream CSV rows and original service clocks 3663/3663/4929/11729/3663/3663
remain exact. Main 213.77 s, auxiliary 186.30 s. This measures observation under
the OLD scheduler; it does not prove service after inserting a capture/replay
barrier into that scheduler.

## Physical evidence and remaining work

Standalone Vivado 2022.2, xc7z010clg400-1, 175 MHz nominal (5.714 ns): one RAMB18
in SDP mode, 36-bit write port B, 75 LUT, 111 FF, zero DSP. All 154 nets route
without errors. Capture-ready and complete writer enable/address controls have
no combinational input from downstream READY. Constants on unused RAM write
pins are not mistaken for an absent RAM; the separate port check requires a
real SDP writer and nonconstant controls.

Timing still fails: WNS -0.181 ns, TNS -7.073 ns, 59/167 setup endpoints fail.
Hold +0.167 ns and pulse +2.357 ns pass. Worst path is descriptor bit 3 through
the 70-bit identity/fault tree to write-count enable, twelve logic levels
(six CARRY4), 5.606 ns data delay. 197 input and 127 output ports are unqualified
by the standalone recipe. This is NOT integrated FFT/full-receiver closure.

Next remove the descriptor/fault tree from private capture progress, or bound
its comparator depth, while preserving same-edge replay/public fault fencing.
Do not waive it. Preserve this source/checkpoint as the measured reference.
Then integrate local bank capacity into the forward guard, feed kernel/product
from sealed replay, and join guard completion with actual bank/product ownership
return before inverse admission. Recompute caller fault predicates: the old
parallel-READY equivalence is an old-topology proof, not reusable authority for
new buffered wiring. Retain fault injection, descriptor/epoch identity and
independent raw-input/status validation in the new integration tests.

Before integrated routing, measure full service including capture, seal,
replay, final product publication and resets. The planning allowance of 512
additional clocks over 3663 (roughly 4175 versus 5215 available) is NOT proven.
Add measured metadata/control and real receiver BRAM use, not just this one
standalone RAMB18. Keep continuous arrivals, retained native evidence, IIO
bandwidth and real clock constraints as separate release gates.

Full receiver timing/CDC/reset, actual 60 MS/s RX calibration, sustained
Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans remain pending. Qualify
pinned PPU/rollback on .18 before .17 Ethernet-only outdoor deployment. No
radios accessed, no PPU/main changes, primary HDL gitlink unchanged; .14/.20/.21
remain excluded.

Raw: /dev/shm/starlink-forward-return.FEyGL1Bw.
Prepared-v2 SHA: 947c2e9fe7a1b8a0acf449fdf32a69cceadef84a3e390a33c5d713bbf3d37824.
Bank RTL SHA: 3bdb52c073d32dbb61032239778a6379f64712342ea5d876e90066e674e7f7d3.
Routed standalone DCP SHA: d6a093f490c167f2a3f8dea9fc61c848db34ed549efb05bbf18dc7c3762f4c33.
