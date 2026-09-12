# Complete coarse detector RTL checkpoint — 2026-09-12

Full goal remains **2.5 / 5 / 15 MS/s FPGA PSS detection with a 2.5 MS/s IIO
inspection stream for independent host GLRT**. This checkpoint is progress,
not completion or deployment. No radio was flashed or reconfigured.

## Implemented

The new detector now performs all of the following in RTL, on one centered
2.5 MS/s accepted sample stream:

1. Exact 16-tap Q15 complex PSS correlation and window energy.
2. Exact normalized uint8 score, ties-to-even, full 75-bit power domain.
3. Rational 750 Hz phase accumulation: phase advances by three modulo 10000.
4. Two real BRAM map banks, each accumulating 29 complete 4 ms groups.
5. Circular three-cell peak search, guarded background moments, and the
   integer z>=8 confidence gate. The host does not make that decision.
6. Explicit startup initialization, gap/overload expiration and fault reporting.

Each map contains 290000 scores / 116 ms / 87 nominal frames, leaving margin
inside a 120 ms dwell for startup and result processing. This is a change from
the original float screen's almost-120-ms accumulation, not a claim to use all
90 frames. Exact complete groups make every phase cell's coverage equal.

The detector has no ready/backpressure output to IQ. An actual independent
IIO/DMA fanout still needs integration. The FPGA reports a candidate every map;
`detected=1` is required for a confidence-qualified result. A below-threshold
peak is not called a PSS detection.

## Complete recorded-dwell RTL replay

Four 120 ms **recorded derivatives**, 300000 CI16 samples each, were fed to
the complete detector at one input per 40 calculation clocks. IQ starts
immediately after reset; initialization is not hidden by waiting for ready.
The expected first admitted map begins at score index 485 after the 200 us
BRAM initialization, and contains exactly 290000 consecutive scores.

| Window | FPGA decision | Phase difference from blind host GLRT | Integer map comparison |
| --- | --- | --- | --- |
| Positive 36.62 s | Detected | 0.333 us | Exact |
| Positive 37.12 s | Detected | 0.067 us | Exact |
| Negative 1.12 s | Not detected | Not meaningful below threshold | Exact |
| Negative 1.62 s | Not detected | Not meaningful below threshold | Exact |

Every first index, peak bin, peak value, background sum, sum of squares,
background count and decision matched the independent integer reference.
The final routed RTL revision passed all four replays. Earlier revisions and
their receipts are retained as well. **91 focused tests pass**, including
full-width extremes, tie rounding, all normalization flush stages, actual
recorded-IQ MAC/scorer composition, circular boundaries, both map banks,
zero/noise cases, index gaps, overload recovery and flushing during a scan.

These are simulation runs, not 120 ms radio captures made today. Input is from
the same known episode and frequency-centered using an earlier pilot CFO
alternative. No PSS output seeds the independent host GLRT reference.
This does not qualify an arbitrary-offset blind 2.5 MS/s receiver, independent
RF timing truth, a general false-alarm rate, or the actual AD9361 filter model.

## Routed resources and timing

The final probe includes the **entire detector**, with registered source/sink
logic, at 100 MHz on xc7z010clg400-1:

- Setup slack **+0.837 ns**; hold slack **+0.067 ns**.
- All twelve `check_timing` categories report zero issues.
- Detector: **1722 LUTs, 2301 FFs, 13 RAMB36 blocks, 36 DSPs**.
- Including probe stimulus/sink: 1733 LUTs, 2588 FFs, same RAM/DSP counts.

This leaves 44 of the device's 80 DSPs and 47 of its 60 RAMB36 blocks before
receiver/filter/IIO integration. It is a concrete budget for **one centered
CFO bank**, not permission to replicate a nine-bank detector.

The probe uses a declared OOC clock origin, not the complete receiver clock
network. Full-board implementation remains mandatory. First attempts failed
BRAM inference because of the multi-port coding pattern; separate RAM-port
processes plus a single address mux per port resolved it. No RAM was dissolved
into registers. The first complete routed detector had +0.173 ns setup; a
register between the RAM/window sum and peak comparator improved the final
margin. The detection arithmetic and thresholds did not change.

## PPU and radio preflight

PPU now distinguishes host-key verification failure before the stdin handshake
from a generic closed connection. The change retains strict SSH checking,
does not enroll keys, and does not disclose transcript text in the new error.
It and its regression tests are pushed to **PPU remote main**, commits
`35c7a9e` and formatting follow-up `9a56643`. The 38 targeted setup tests and
Ruff lint pass. The original PPU worktree's four preexisting dirty files were
not changed or published. Its preexisting whole-file formatting differences
were also left alone.

Read-only, globally serial-locked attempts using additional existing .17
known-hosts files did not attest the radio. A bounded command exposed the
specific error: no ED25519 key for 192.168.1.17 was present in the selected
alternative pin file; the earlier persistent pin instead reported a changed
key. Neither condition was bypassed, and no key file was changed.

Allocated radios remain .18 serial `1040007c4a94000211000b009186843ef2` and
.17 serial `104000bac4950008230026001b440a003a`. .18's previous exact USB
identity observation remains available; no .18 operation occurred in this
continuation. No TX operation or use of .14/.20/.21 occurred.

## Remaining path to deployment

1. Integrate the detector and independent 2.5 MS/s IQ capture behind a small
   control/metadata interface. Bind candidate indices to the same admitted
   sample counter as the exported IQ; preserve explicit template/filter delay.
2. Add/verify the 2.5, 5 and 15 MS/s source conditioning profiles. The detector
   stays at 2.5 MS/s. Earlier wider-rate offline searches are not evidence that
   these actual FPGA rate-conversion/ADC profiles are complete.
3. Build and route the full receiver; qualify reset/stop/DMA stalls/gaps and
   sustained 10 MB/s CI16 payload. Candidate delivery and capture receipts need
   their own loss/continuity checks.
4. Deploy a pinned canary through PPU to .18, verify actual RX rate/calibration,
   deterministic common-stream injection, 120 ms and 300 s IIO captures and
   host replay agreement, plus clean stop/restart and rollback.
5. Resolve .17's trusted SSH identity without weakening verification; deploy
   over Ethernet PPU only after the canary passes, then verify outdoor PSS
   decisions against blind host GLRT on the exported IQ.

No release package or full-board image from this fresh architecture exists
yet. The original 05:32–13:32 UTC feasibility timebox is not extended. The
full goal remains active; it has not been replaced by an IQ-only milestone.

## Evidence

- [Final complete-dwell RTL results](reports/coarse25-detector-replay-20260912.json)
- [Routing and replay evidence archive](reports/coarse25-detector-evidence-20260912.tar.gz)
  SHA256 `507abca3e37fb63d78d9541baef7f9e33cbd304a9ac5349269e1ae54583f8d53`.
- Raw final route:
  `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/fresh-coarse25-artifacts.ZwJPCrqH/detector-v4`.
- Raw final replay:
  `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/fresh-coarse25-artifacts.ZwJPCrqH/detector-replay-v4`.
- [Interface and arithmetic contract](hdl/library/starlink_coarse25/README.md).

The archive includes failed inference logs, intermediate routed checkpoints,
final routed checkpoints, frozen replay plans and results, and final simulation
logs. Input-memory files are reproducible from the hash-pinned CI16 exports;
they are not duplicated into this archive.
