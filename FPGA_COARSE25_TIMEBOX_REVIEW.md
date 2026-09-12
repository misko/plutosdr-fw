# Fresh coarse25 timebox review — 2026-09-12 15:00 UTC

**Outcome: useful subsystem progress, deployment gate not met.** The original
05:32:24–13:32:24 UTC feasibility budget has expired. At the 14:59 UTC clock
check work stopped for this go/no-go review. No new implementation or full-board
build is authorized by silently extending that budget. Saving source/evidence
does not constitute a release. The full 2.5 / 5 / 15 MS/s goal is not complete.

## Completed since the detector checkpoint

- Added C251, a distinct 2.5 MS/s bypass capture identity using the existing
  tested CI16 FIFO and stop/drain lifecycle. The detector receives the exact
  FIFO-admitted IQ prefix, independently of DMA delivery cadence.
- Added coherent latest-result snapshots, sequence numbers, decision/quality
  fields and detector-fault counters. Sequence gaps identify missed results;
  this is explicitly not a lossless event queue.
- Eight new integration tests pass: exact IQ/index mapping, exact second map,
  immutable snapshots, overflow/source gaps/flush and finite stop/rearm.
- All 72 original capture tests pass. Another 179 build-admission, control-stage
  and existing CDC tests pass. These are focused tests, not the whole repository.
- Routed capture+detector+AXI subsystem at 100 MHz: +0.874 ns setup, +0.021 ns
  hold, zero issues in all twelve timing-check categories. Actual capture block:
  2889 LUT, 4174 FF, 13 RAMB36, 36 DSP. The registered harness is not a full board.
- Added a draft `coarse25` board profile: one RX, existing loss-detecting CDC,
  C251 capture/detector and 32-bit AXIS DMA. It excludes old acquisition FFT,
  native tracker and raw timestamp DMA. Build admission accepts only explicit
  `STARLINK_PSS_PROFILE=coarse25 STARLINK_PSS_RATE_MSPS=2.5`.
- Packaged the ingress, capture, AD9361 and DMA dependencies successfully.
  **The full block design has not been elaborated, synthesized or routed.**
- Created a clean bulk-backed Linux worktree on the do-not-merge branch from
  4357f41a721d. No Linux code was changed. Its existing PIL1 driver correctly
  rejects C251; C251 IIO driver support remains unimplemented.

The first capture OOC probe passed setup (+0.542 ns) but failed hold (-0.225 ns)
at an external AXI input. The subsequent registered fabric-boundary probe passes;
both reports/checkpoints are retained, with no claim that this fixes or qualifies
actual board input timing.

## Not completed / no deployment claim

1. Full-board build, constraints/CDC audit and routed setup/hold verification.
2. C251 Linux/IIO snapshot and IQ support, plus host capture/replay tooling.
3. Physical 2.5 MS/s RX calibration and RF-filter/template/epoch qualification.
4. .18 deterministic common-stream hardware check, 120 ms and 300 s host
   captures, byte/count/continuity checks and independent GLRT comparison.
5. .17 trusted SSH identity recovery, PPU Ethernet deployment and outdoor test.
6. Actual 5 and 15 MS/s FPGA conditioning profiles; earlier offline wider-rate
   diagnostics are not these implementations. 30/60 remain later milestones.

Allocated radios remain .18 `1040007c4a94000211000b009186843ef2` and .17
`104000bac4950008230026001b440a003a`. Neither was flashed or reconfigured in this
fresh effort. .17's saved SSH trust mismatch remains unresolved. No new radio
operation occurred in this continuation; no .14/.20/.21 or transmitter was used.
No fresh release image or deployment package exists. PPU diagnostic changes
from the earlier checkpoint are already pushed to its remote main (9a56643).

## Recommendation for the decision

Preserve the original deployed reference. If continuing is approved, bound the
next increment to **one 2.5 MS/s .18 canary**: full board, C251 IIO, a 120 ms
common-stream verification, then 300 s. Keep the detector enabled; do not relabel
an IQ-only result as the goal. Do not start 5/15 filtering or outdoor rollout
until this canary passes. Set a new explicit time budget and stop condition first.
Otherwise archive this branch as a viable subsystem experiment and abort rollout.

## Evidence locations

- [C251 contract](hdl/library/axi_starlink_pilot_capture/COARSE25_ABI.md)
- [Earlier complete detector checkpoint](FPGA_COARSE25_DETECTOR_CHECKPOINT.md)
- [Capture routing evidence archive](reports/coarse25-capture-routing-20260912.tar.gz),
  SHA256 `c395d49f25ad5cdd3a28dcd6cd80647c10650b0b069a29b5af39a1d76e927a19`.
- Raw capture routes: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/fresh-coarse25-artifacts.ZwJPCrqH/capture-v1`
  and sibling `capture-v2` (including synthesis and routed checkpoints).
- Integration tests: `tests/starlink_oracle/test_coarse25_capture_rtl.py`.

Firmware/HDL branch: `codex/pss-coarse25-do-not-merge`, never merge to main.
