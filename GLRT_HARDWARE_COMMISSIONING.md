**Ethernet commissioning record — 9 September 2026, active**

The user authorized implementation, testing, deployment and verification on a
locally USB-connected receiver, excluding serial
`1040007c4a94000211000b009186843ef2`. The selected receiver is
`winbond-db620818a328172c`, Ethernet `192.168.1.14`, local USB `5-1`.
All deployment, configuration and capture operations use Ethernet. USB presence
is checked for recoverability. The excluded receiver is not operated.

Build and test evidence is under `/srv/bulk/leo/glrt-deployment-20260909`.
Private recovery material and detailed operator receipts are under the owned
device tool's `artifacts/ethernet-canary-14` directory. Those files are not added
to Git. The original persistent v0.47 FIT has been extracted and independently
verified; it differs from the original active v0.48 RAM image.

| Image | HDL | Linux | Routed setup / hold slack | Commissioning state |
|---|---|---|---|---|
| `glrt-eth-r2500000-v1` | `625a93e7` | `36c6561f` | +0.009 / +0.020 ns | Reconciled exact running FIT; PN and short/backlog captures passed |
| `glrt-eth-r2500000-v2` | `625a93e7` | `93a343f2` | +0.009 / +0.020 ns | PN, short capture, two complete ten-second captures and 320-event control passed; exact original rollback passed |
| `glrt-eth-r5000000-v1` | `ec87261d` | `93a343f2` | +0.013 / +0.017 ns | Deployment, PN, short and ten-second IQ/event capture, and blind host comparison passed |
| `glrt-eth-r10000000-v1` | `ec87261d` | `93a343f2` | +0.055 / +0.035 ns | Deployment, PN, short and ten-second IQ/event capture, and blind host comparison passed |
| `glrt-eth-r25000000-v1` | `4cd97a03` | `93a343f2` | +0.004 / +0.025 ns | Currently deployed; PN, short and ten-second IQ/event capture, blind host comparison and idle attestation passed |

Each image exports continuous 2.5 MS/s CI16 IQ. Its source rate is attested from
the public FPGA snapshot before any PHY rate change. The 25 and 60 MS/s ec872
builds failed timing and are excluded from deployment. The reviewed idle-payload
change closes timing at 25 MS/s. Its 60 MS/s build and one fixed physical retry
both failed setup at -0.199 ns and were not deployed. A subsequent exact pilot
bank row precomputation (`6099b304`) passed focused numerical, cycle-timing and
finite-close checks; its fresh full 60 MS/s build and independent five-rate
matrix are in progress. No clock or timing constraint has been relaxed.

The full 5/10 MS/s implementation audits were reviewed alongside the accepted
2.5 MS/s canary. They contain one GLRT IP and DMA, no PSS and no native ADC DMA,
complete routing, passing internal timing and passing Gray-bus skew. They add
no data clock crossing. They retain the existing reset-release fanout/Gray/ADI
CDC warnings and 13 RX input plus two ENSM output ports without external delay
constraints. Exact reports and limitations are recorded in
`HIGHER_RATE_EC872_PHYSICAL_REVIEW.md` under the evidence root. These findings
permit bounded experimental commissioning under the user's instruction, with
an independently inspected current-rate RX PN eye before interpreting captures.
They do not establish production or live-detector qualification.

Commissioning proceeds through a calibrated short capture, a bounded event
transport control with decisions disabled, a ten-second continuous IQ check,
and independent host processing of retained IQ. Normal captures retain the
frozen `glrt-upper-candidate-v1` gates. The separate event transport control is
explicitly labeled custom development and cannot establish sensitivity.
Exact original persistent rollback was exercised successfully before returning
to GLRT at 5 MS/s. Every transition requires its own frozen source and
target FIT, serial, layout, idle-state and TX-safe checks.

All completed captures so far use the observed post-boot 2.4 GHz LO, 2 MHz
bandwidth, A_BALANCED RX and manual 30 dB gain, with TXLO powered down and
TX gain at -80 dB. Neither that LO nor historical bench notes identifies the
current RX1 feed. Current antenna/LNB connection and IF remain unknown.

Three real collector failures are preserved. The first short capture read final
counters before IIOD finished asynchronous kernel buffer teardown; the fix
waits for the matching visit's final snapshot. The first ten-second capture
received its full 100 MB, but its quiet event socket retained a ten-second
timeout because the timeout was changed after buffer OPEN. The fix sets it
before OPEN and disqualifies event transport on reader error even if counts
match. Neither failed capture is relabeled as successful.

The larger-buffer ten-second runs each saved all 25 million IQ samples in about
10.07 seconds, with zero faults, clipping, busy rejections or pending work.
They used 250,000-sample chunks and four requested kernel buffers. The earlier
25,000-sample-chunk run overflowed the 256-word FPGA output FIFO. Its counters
prove downstream backpressure, without identifying a host/kernel/DMA cause.
The successful larger-buffer run's FIFO high water was one. Use the measured
larger-buffer configuration for long commissioning; do not hide the failed run.

The decisions-off 120 ms control transported all 320 native score records.
Conditional integer recomputation from the same 2.5 MS/s saved IQ matched every
event's energies, peaks, bins, flags, block shift and Q16 scores exactly, with no
excluded events. Its absolute epoch origin exceeded 2^32. The report is
`hardware-2500000-event-control-v2-oracle-v1/REPORT.md` under the evidence root.
This is arithmetic verification using the recorded epochs, separate from the
unseeded host detector. Busy/expiry counts induced by the artificial zero
acquisition gate are explicitly retained.

Normal ten-second captures at each commissioned source rate saved all
25 million output samples, with exact IQ/event and finite-close accounting.
There were no busy rejections, expiry, incomplete tails, clipping, transport
faults or pending work. Every output FIFO high water was one.

| Source MS/s | Capture / visit | Elapsed including stop, s | Scored events | RX PN passing eye points |
|---|---|---|---|---|
| 2.5 | `v2-2500000-10sec-large-buffers-v1` / 909507 | 10.069882 | 0 | 141 |
| 2.5 repeat | `v2-2500000-10sec-large-buffers-v2` / 909509 | 10.068877 | 0 | Same unchanged calibration |
| 5 | `rate5000000-10sec-v1` / 909511 | 10.065150 | 1,560 | 150 |
| 10 | `rate10000000-10sec-v1` / 909513 | 10.061013 | 2,549 | 159 |
| 25 | `rate25000000-10sec-v1` / 909515 | 10.068624 | 3,497 | 161 |

PN eyes were measured in each rate's preceding 120 ms commissioning operation;
each selected RX delay was 0x08, independently checked within its passing eye.
These score records contain no positive detector decisions.

Independent blind host analysis of one normal ten-second capture at each of
2.5, 5, 10 and 25 MS/s completed all 1,000 overlapping windows per recording
and found no multi-frame pilot positives. Every comparison completed with no
unmatched or unobservable FPGA positive. The 5/10/25 MS/s comparisons still
retain 1,493/1,478/1,512 unmatched individual-frame host engineering supports;
those overlapping, uncalibrated supports are not known misses or independent
false-alarm trials. The separate decisions-off control also had no multi-frame
host positives, with 15 individual-frame engineering supports retained.
Reports are `host-live-<rate>-10sec-v1` and
`compare-live-<rate>-10sec-v1.json` under the evidence root (the 2.5 MS/s names
use `v2-2500000`). This quiet observation does not establish live sensitivity
or nonvacuous detector agreement. Hardware-qualified flags remain false.

At 06:07 UTC, an independent read-only check verified the currently deployed
25 MS/s label, serial, FIT SHA-256
`61c05dfea20f8758e1ec250843bb9358dbbf27db4b9c0fe616df1c7399c42cb0`,
GLR1/GLX1, AD9361, gigabit/full-duplex Ethernet, both disabled buffers and TX mute.
All eight recorded U-Boot fields matched the original verified baseline,
including absent `attr_name`/`attr_val`. The retained private receipt is
`current-25000000-idle-state-v1.json`, SHA-256
`174d3f9eab559431b7ae81720216ddfafc71d1b54fff4eaf4a17766039ab0363`.
This is a timestamped state observation; later operations require their own
current identity and idle checks.
