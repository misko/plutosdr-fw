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
| `glrt-eth-r2500000-v2` | `625a93e7` | `93a343f2` | +0.009 / +0.020 ns | Full Ethernet deployment return passed; AD9361 verified; PN and 120 ms capture passed |
| `glrt-eth-r5000000-v1` | `ec87261d` | `93a343f2` | +0.013 / +0.017 ns | Package verified; hardware checks pending |
| `glrt-eth-r10000000-v1` | `ec87261d` | `93a343f2` | +0.055 / +0.035 ns | Package verified; hardware checks pending |

Each image exports continuous 2.5 MS/s CI16 IQ. Its source rate is attested from
the public FPGA snapshot before any PHY rate change. The 25 and 60 MS/s ec872
builds failed timing and are excluded from deployment. Fresh builds with the
reviewed idle-payload timing change are underway.

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
Exact original persistent rollback is then exercised before proceeding through
the timing-passing rates. Every transition requires its own frozen source and
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

The corrected image's short capture and independent host comparison contain no
FPGA or host pilot positives. That verifies quiet transport and accounting;
live pilot agreement remains unproven. Hardware-qualified flags remain false.
