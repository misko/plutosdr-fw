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
| `glrt-eth-r5000000-v1` | `ec87261d` | `93a343f2` | +0.013 / +0.017 ns | Deployed successfully from restored original v0.47; receive checks pending |
| `glrt-eth-r10000000-v1` | `ec87261d` | `93a343f2` | +0.055 / +0.035 ns | Package verified; hardware checks pending |
| `glrt-eth-r25000000-v1` | `4cd97a03` | `93a343f2` | +0.004 / +0.025 ns | Full build audit passed; package preparation underway |

Each image exports continuous 2.5 MS/s CI16 IQ. Its source rate is attested from
the public FPGA snapshot before any PHY rate change. The 25 and 60 MS/s ec872
builds failed timing and are excluded from deployment. The reviewed idle-payload
change now closes timing at 25 MS/s; the fresh 60 MS/s build remains in progress.

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

Two real collector failures are preserved. The first short capture read final
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

Independent blind host analysis of the normal ten-second capture completed all
1,000 overlapping windows and found no pilot positives, matching the FPGA's
quiet observation. The separate decisions-off control also had no multi-frame
host positives, while 15 individual-frame engineering supports are retained in
its comparison. These uncalibrated metrics do not establish live sensitivity.
Live pilot agreement remains unproven; hardware-qualified flags remain false.
