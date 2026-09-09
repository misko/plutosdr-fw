**Experimental Ethernet commissioning record — 9 September 2026**

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
| `glrt-eth-r25000000-v1` | `4cd97a03` | `93a343f2` | +0.004 / +0.025 ns | PN, short, ten- and thirty-second captures passed; intentional failure controls and clean restart verified |
| `glrt-eth-r60000000-v1` | `5e28d175` | `93a343f2` | +0.075 / +0.017 ns | Currently deployed; PN and short/ten-/thirty-second transport and closure checks passed; two candidate expirations in each long run |

Each image exports continuous 2.5 MS/s CI16 IQ. Its source rate is attested from
the public FPGA snapshot before any PHY rate change. The 25 and 60 MS/s ec872
builds failed timing and are excluded from deployment. The reviewed idle-payload
change closes timing at 25 MS/s. Its 60 MS/s build and one fixed physical retry
both failed setup at -0.199 ns and were not deployed. A subsequent exact pilot
bank row precomputation (`6099b304`) passed the full fresh five-rate numerical
matrix and finite-close checks, but its 60 MS/s build failed setup at -0.223 ns.
Its final worst paths moved to AXI command/fault decoding. The final `5e28d175`
change registers four generic byte-zero flags on the existing AXI write-data
dispatch edge and uses them for wide command predicates. Data, strobes,
acknowledgments and command effects retain their original cycle alignment.
That 60 MS/s implementation passes setup at +0.075 ns and hold at +0.017 ns.
No clock or timing constraint has been relaxed.

All five passing implementations were independently audited. They contain one
GLRT IP and DMA, no PSS and no native ADC DMA,
complete routing, passing internal timing and passing Gray-bus skew. They add
no data clock crossing. They retain the existing reset-release fanout/Gray/ADI
CDC warnings and 13 RX input plus two ENSM output ports without external delay
constraints. Exact reports and limitations are recorded in
`HIGHER_RATE_EC872_PHYSICAL_REVIEW.md` under the evidence root. These findings
permit bounded experimental commissioning under the user's instruction, with
an independently inspected current-rate RX PN eye before interpreting captures.
They do not establish production or live-detector qualification. The final
60 MS/s image occupies all 4,400 slices, 48 of 60 BRAM tiles and 72 of 80 DSPs,
with 13,941 LUTs and 15,038 flip-flops. Its 31,484 routable nets all route;
internal setup/hold, Gray-bus skew, clock and exception checks pass. Full slice
occupancy, small margins and the retained external timing/CDC gaps limit the
claim to the tested board and configuration.

The final numerical core and its 40-file scientific source inventory are
byte-identical to `6099b304` across all fifty fresh seed-50917 replay cases.
That inventory includes 34 HDL/template files plus bench/oracle/profile inputs.
The retained matrix recovers all 45 complete strong frames and leaves all fifteen controls
quiet, with exact exported IQ and integer scores. This is verified source
identity carrying forward that matrix, not a new fifty-case `5e28d175` run.
Current AXI/boundary/capture tests and twenty independent all-rate finite-close
fixtures check the changed interface. A fresh full 24-record saved upper-edge
replay on `5e28d175` also passed: 1.2 million IQ samples and 116 scores are exact,
with one independently matched FPGA positive and 148 unmatched deduplicated
host support groups retained. These previously examined 20 ms, 2.5 MS/s records
are development evidence, not curated native higher-rate RF truth. Reports are
under `saved-upper-5e28d175-batch-v1` and `rtl-axi-5e28d175-independent-v1`.

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

The corrected 2.5 MS/s larger-buffer ten-second runs each saved all 25 million
IQ samples in about 10.07 seconds, with zero faults, clipping, busy rejections
or pending work.
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
There were no incomplete tails, clipping, transport faults or pending work.
Every output FIFO high water was one. At 2.5/5/10/25 MS/s there were no busy
rejections or expiry. At 60 MS/s, two selected candidates expired before native
processing in each of the ten- and thirty-second runs. These are real candidate
admission losses, separately counted from loss-free IQ and completed-event
transport; normal candidate admission at 60 MS/s is not lossless.

| Source MS/s | Capture / visit | Elapsed including stop, s | Scored events | RX PN passing eye points |
|---|---|---|---|---|
| 2.5 | `v2-2500000-10sec-large-buffers-v1` / 909507 | 10.069882 | 0 | 141 |
| 2.5 repeat | `v2-2500000-10sec-large-buffers-v2` / 909509 | 10.068877 | 0 | Same unchanged calibration |
| 5 | `rate5000000-10sec-v1` / 909511 | 10.065150 | 1,560 | 150 |
| 10 | `rate10000000-10sec-v1` / 909513 | 10.061013 | 2,549 | 159 |
| 25 | `rate25000000-10sec-v1` / 909515 | 10.068624 | 3,497 | 161 |
| 60 | `rate60000000-10sec-v1` / 909522 | 10.064262 | 3,635 | 174 |

PN eyes were measured in each rate's preceding 120 ms commissioning operation;
each selected RX delay was 0x08, independently checked within its passing eye.
These score records contain no positive detector decisions.

Independent blind host analysis of one normal ten-second capture at each of
2.5, 5, 10, 25 and 60 MS/s completed all 1,000 overlapping windows per recording
and found no multi-frame pilot positives. Every comparison completed with no
unmatched or unobservable FPGA positive. The 5/10/25 MS/s comparisons still
retain 1,493/1,478/1,512 unmatched individual-frame host engineering supports;
the 60 MS/s comparison retains 1,641 in-band supports and 578 out-of-band ones.
Those overlapping, uncalibrated supports are not known misses or independent
false-alarm trials. The separate decisions-off control also had no multi-frame
host positives, with 15 individual-frame engineering supports retained.
Reports are `host-live-<rate>-10sec-v1` and
`compare-live-<rate>-10sec-v1.json` under the evidence root (the 2.5 MS/s names
use `v2-2500000`). This quiet observation does not establish live sensitivity
or nonvacuous detector agreement. Hardware-qualified flags remain false.

At 06:07 UTC, an independent read-only check verified the then-deployed
25 MS/s label, serial, FIT SHA-256
`61c05dfea20f8758e1ec250843bb9358dbbf27db4b9c0fe616df1c7399c42cb0`,
GLR1/GLX1, AD9361, gigabit/full-duplex Ethernet, both disabled buffers and TX mute.
All eight recorded U-Boot fields matched the original verified baseline,
including absent `attr_name`/`attr_val`. The retained private receipt is
`current-25000000-idle-state-v1.json`, SHA-256
`174d3f9eab559431b7ae81720216ddfafc71d1b54fff4eaf4a17766039ab0363`.
This is a timestamped state observation; later operations require their own
current identity and idle checks.

Additional bounded 25 MS/s operation checked longer transport and recovery.
The 30-second normal capture (`rate25000000-30sec-v1`, visit 909516) saved
300 MB in 30.181149 seconds with all 10,381 score records, no positive
decisions, FIFO high water one and clean transport/detector/closure counters.
The blind host completed all 3,000 windows without a multi-frame positive;
the comparison retains 4,602 unmatched overlapping individual-frame supports.

Three separate intentional controls requested three seconds each with unchanged
normal gates and 250,000-sample chunks. Each started its local process signal
only after at least 2 MB of actual IQ had been saved, with exact PID identity
and separate control receipts. They are operational tests, not detector trials.

| Control / visit | Observed result | Cleanup |
|---|---|---|
| Operator interruption / 909517 | Failed as intended; 1,000,000 samples saved of 7,500,000 requested, while fabric/AXIS delivered 1,286,752; all 171 events drained and finite accounting settled | Graceful collector SIGINT, no kill escalation; exact identity and both idle buffers verified |
| Collector pause, measured 150.130 ms / 909518 | Complete 30 MB and all 1,002 events, no faults, FIFO high water one | Both buffers idle and TX mute verified |
| Collector pause, measured 700.113 ms / 909519 | Failed explicitly with output FIFO overflow and broken pipe; 1,500,256 samples reached AXIS and 1,500,000 were saved, high water 256; all 197 events and finite accounting still drained | Both buffers idle and TX mute verified; no escalation |

These controls measure those individual pauses at their recorded points; they
do not establish a universal stall tolerance or sustained spare capacity.
Their original failed capture/operator receipts remain failed. A fresh normal
one-second capture after the induced overflow (`rate25000000-restart-1sec-v1`,
visit 909520) then saved all 10 MB and 335 score records in 1.042284 seconds,
with clean counters, settled closure and verified idle state. Its blind host
analysis completed all 100 windows without multi-frame positives, and its
capture comparison completed without unmatched or unobservable FPGA positives.

The final 60 MS/s package uses HDL `5e28d175d58d7aad73a714017624c74e2bf34e93`
and Linux `93a343f2971762f7c8c3d0dba0d9a5934b9e3986`, assembled from firmware
`e61b8f5457851ec9e1c091026dd6b1b4d881aef6`. Independent extraction verifies the
exact XSA/bitstream, kernel, DTB and rootfs inputs. The persistent FRM is the
12,973,835-byte FIT plus its 33-byte MD5 trailer. Exact deployed FIT SHA-256 is
`02c5dae000e7d0549eb52e757cff52d24d56a51f58d9cd00206840a99d011009`;
FRM SHA-256 is
`3ad0184e975f8cf187b9f3f66f00fd7497146d282d4a65d4692681bf41ed251b`.
The successful 25-to-60 MS/s persistent transition receipt is
`rate60000000-forward-receipts/47fe3240-503b-4d6a-b2ad-e973104ab29c.json`,
SHA-256 `5709ebde217114851c2f0fa775e6867da3ea153a78a700f6556232b1207b88ce`.
It verifies the exact returning FIT, serial, AD9361 layout, Ethernet and TX mute.

Its current-rate RX PN eye has 174 passing points; selected delay 0x08 is
clock-delay zero, data-delay eight, independently checked at row eight/column
zero. Calibration restores the BIST/debug/RF state. The 120 ms capture
(`rate60000000-120ms-v1`, visit 909521) saved all 1.2 MB and 44 score records,
with zero candidate losses and clean transport/closure. Its independent host
processed twelve windows without a multi-frame positive; 21 in-band and three
out-of-band individual-frame supports remain visible.

The 60 MS/s thirty-second capture (`rate60000000-30sec-v1`, visit 909523) saved
all 300 MB and 10,824 scored events in 30.199252 seconds. Like its ten-second
predecessor, it has exactly two busy rejections, both classified as expired
candidates, and no transport fault, DDC clipping, incomplete tail or pending
work. All completed native vectors, scores and CPU event records reconcile.
Both operators exited successfully and independently verified the exact image,
both disabled buffers and TX mute afterward. Their IQ SHA-256 values are
`271f85a41f1473fe1100801ae734317c46363353de95a14d89008aea22532200` (ten seconds)
and `e5a48c65a1542bf33ceb673180411ee6e3ba243fe415d734e510bf59094c8e17`
(thirty seconds).

The final thirty-second blind replay completed all 3,000 windows in 375.23
seconds. It found no multi-frame host or FPGA positives and retains 4,641
unmatched in-band individual-frame supports plus 1,859 out-of-band supports.
The exact-IQ comparison reports `agreement_observed=false`; this is complete
independent processing of quiet bench IQ, not demonstrated live pilot agreement.
Across all three 60 MS/s captures, IQ components remain within -3 to +3 with
no integer rails. The thirty-second refill median/p95/maximum were
100.005/101.290/116.415 ms for 1 MB blocks. The combined source-bound report is
[the 60 MS/s analysis](/srv/bulk/leo/glrt-deployment-20260909/analysis-live-60000000-all-v1/REPORT.md).

The final independent read-only state check completed at 07:17:37 UTC on boot
`1fdc9551-de3c-4333-ac36-7d7b16933dc2`. It verified the current 60 MS/s image,
exact FIT and serial, local USB recovery presence, AD9361, GLR1/GLX1 geometry,
gigabit/full-duplex Ethernet, both disabled buffers, the recorded RX settings
and TX mute. All eight U-Boot fields still match the original hash-verified
baseline; pinned SSH trust is unchanged. The receipt
`current-60000000-idle-state-v1.json` has SHA-256
`8514ff3a638309991e37f0725196f140d125a95e765678d347b9c67fd674de17`.
The check held the shared device lock and changed no RF configuration, firmware,
U-Boot settings or SSH trust. Reading public counters performs the driver's
ordinary snapshot-latch operation.

This is an experimental local persistent deployment. A controlled cold power
return, calibrated live sensitivity/false-alarm envelope, known pilot-bearing
RF feed and outdoor deployment are not established by these measurements.
The excluded receiver remains untouched. Reuse the retained IQ for analysis;
further RF collection requires its own bounded purpose and authorization.
