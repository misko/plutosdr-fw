# Actual FFT and buffers: replay improvement, writer-stage regression

The simpler controller is integrated with the real generated FFT, descriptor
ledger and payload buffers. This increment separates private replay progress
from actual bank publication, then experiments with a registered writer
descriptor comparison. Both versions pass their actual-FFT simulations;
**neither passes routed timing and neither is deployed**.

## What passed

- Each version independently matches all **64,512 numerical records** from the
  pinned reference. V1 and V2 numerical CSVs are byte-identical. Six healthy
  numerical/backpressure contexts and all previous reset/fault checks remain.
- Five new replay-boundary cases prove that coincident faults or resets cannot
  produce an unauthorized publication or release. The private controller may
  advance while actual bank authorization is vetoed; notification still requires
  the real bank request transition, and release requires the real reader ACK.
- Four additional V2 cases cover faults, resets and captured-descriptor
  corruption while validation is pending. No pending descriptor may authorize
  output. The earlier live-lookup corruption test now also verifies that the
  captured mismatch cannot disappear when the live lookup is restored.
- **366 regression tests pass in 48.35 seconds.** Actual V2 generated-FFT
  simulation passes in 103.11 seconds; synthesis and route complete in
  103.73 and 53.72 seconds with source/checkpoint checks unchanged.
- Normal service remains **3659 fast clocks**, qualifying stalled service 4927,
  below the unchanged 5215-cycle bound at diagnostic 175 MHz. The deliberately
  9000-clock-stalled reader is excluded from that service claim, as before.
  This does not establish continuous native 60 MS/s operation.

## Physical result

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Completion/private-ROM reference | -3.134 ns | -1304.699 ns | 1398 |
| V1 private replay separation | **-2.265 ns** | **-1021.803 ns** | **936** |
| V2 staged writer comparison | -3.251 ns | -1733.553 ns | 1364 |

V1 improves the measured route, but remains failing. V2 removes the long lookup
plus comparison from the worst path and exposes a worse capture-enable path:
publication-controller phase → bank metadata checks → shared fault qualification
→ `output_complete_accept` → descriptor register enables. The signal has fanout
181. The worst path ends at `output_descriptor_expected_reg[59]/CE`, with
12 logic levels and 8.712 ns data delay, including 6.768 ns routing.

V2 hold +0.070 ns and pulse +1.830 ns pass; 8293 nets route with zero errors.
Resources: 2717 LUT / 5653 FF / 21 DSP / 15 RAMB18. Five critical CDC findings,
208 warnings and 114/124 unconstrained I/O remain. Device, generated FFT,
diagnostic 100/175 MHz clocks and route recipe are unchanged. No timing waiver
or full-receiver/board signoff is claimed. V2 remains a recorded experiment,
not an accepted timing improvement over V1.

## Next gate and deployment path

Separate private descriptor-data capture from authorization, with a local
registered ownership/capacity condition. Retain the actual completion receipt,
descriptor comparison, current-fault publication veto and final-reader ACK.
The held reader bundle must freeze while live: simply making all data registers
free-running would be unsafe. Test invalid-input churn, pending validation,
fault-edge capture, reset, held-bundle stability and real release; then repeat
the actual FFT campaign and route before adding features. V1 remains the better
measured replay reference.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required, not removed or newly qualified by this experiment. Full receiver
routing/CDC/reset/board constraints, sustained capture and actual 60 MS/s RX
calibration precede a reversible `.18` canary, then `.17` via PPU Ethernet with
pinned rollback. Finish with the 300-second, 120 ms valid-dwell scan and blind
host GLRT comparison. No radio, PPU, main branch or primary production HDL
gitlink was changed.

## Preserved evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Both versions retain `staged-replay-prepared-vN`, `staged-replay-actual-vN`,
`staged-replay-synth-vN` and `staged-replay-route-vN`. Actual, synthesis and route
processes are terminal. The independent route audit checks source/checkpoint
identity, clock pairs, global timing, complete routing and resources.

V2 inventory: `e56eb3ffa0c1dbe54ca0a7e21b78b84f5c84aa969d3352cbc452470e311da589`.
V1/V2 CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
V2 synthesis DCP: `bcea3aaf3f92d81e4a8b38ece9591fde82921569e145dc8807c3347a29290850`.
V2 routed DCP: `1ac50cfab8c5e22e7b3bc9397411ab864252d04c1a56625e688cb8c90349f816`.

[Verified source/results archive](20260911-staged-replay-evidence.tgz):
26,110,312 bytes, 10,505 regular members, all read-back checked by SHA256 and
size. SHA256: `19e62c12bff186551f37f7327641cf844e74520aa4aa0c51e2d0e578456837bc`.
Both frozen variants, actual logs/CSV, synthesis/routed attempts and test/audit
evidence are included. V1's orchestration source was reconstructed and verified
against its originally recorded hash; V2 directly preserves its runner source.

Implementation pushed to remote `codex/starlink-rx-only-do-not-merge-rom-prefetch`:
FW `d29d076b3909a361fbbbc97785dfd067df74c468`,
HDL `8c8568646650aee1577e96e65d263f49dd09073d`. No merge into main.
