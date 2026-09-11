# GLA1 local search interface (release candidate)

GLA1 selects direct 2,500,000 CI16 samples/s and autonomous upper-edge GLRT.
It excludes the legacy scorer, native 60 MS/s refinement and native scheduler.
GLR1, GLX1 and GLF1 persisted formats remain unchanged. This interface is not
yet a deployed hardware result.

The local engine consumes exactly the IQ words admitted to the independent DMA
prefix. Every 250,000 samples it attempts a 14,000-sample search. An occupied
coarse buffer skips that opportunity; it does not shift the cadence. The search
covers 3,333 epochs and 11 coarse CFO bins, then verifies up to eight candidates
with full-pilot, even/odd and control evidence. CFO output units are 100 Hz.
This is 5.6% acquisition coverage at the initial 100 ms cadence when no windows
are skipped, not a measurement on every 750 Hz repeat.

## Records

Each little-endian record contains 16 unsigned 32-bit words. Candidate evidence
precedes a final decision for each completed window. The FIFO holds 16 records,
keeps the head unchanged until POP and backpressures arithmetic when full.

| Word | Meaning |
| --- | --- |
| 0 | Magic `0x474c4131` |
| 1 | Nonzero visit ID |
| 2 | Zero-based sequence within the visit |
| 3–4 | Window first source index, low word first; preserve integer precision |
| 5 | Flags described below |
| 6 | Signed 32-bit CFO in 100 Hz units, range −4000 through +4000 |
| 7–11 | Coarse, acquire, verify, control and conditioned Q16 scores |
| 12 | Window length, 14000 |
| 13–15 | Reserved, zero |

Flags: bit 0 final decision; bits 1–5 rejection reasons (no candidate, insufficient
support, score, margin, alias); bits 6–8 frame support (0–4); bits 9–11 rank (0–7);
bits 12–15 coarse CFO bin (0–10); bits 16–27 epoch (0–3332); bits 28–31 zero.
The empty decision has flags 3 and zero words 6–11. A nonempty final decision
repeats its winning candidate's payload, with decision/rejection flags added.
Candidate records have no rejection reasons. Zero reasons on a final decision
means supported by the implemented thresholds, not independently identified RF.

## MMIO and snapshots

The additive page starts at byte `0xc00`; all offsets below are relative bytes.

| Offset | Register |
| --- | --- |
| 0x00/04 | Magic/version (`0x00010000`) |
| 0x08/0c | Status/faults |
| 0x10 | Command: 1 POP, 2 latch snapshot, 4 explicit abort after source close |
| 0x14/18/1c | Period/window/FIFO depth |
| 0x20/24/28 | Queue count/high water/snapshot generation |
| 0x2c/30 | Buffered/popped records |
| 0x34/38/3c | Opportunities/admitted/skipped windows |
| 0x40/44/48/4c | Completed/supported/aborted/outstanding windows |
| 0x54/58/5c | Source rate/CFO unit/record word count |
| 0x60–6c | First/last admitted source indices, each low word first |
| 0x70 | Epoch count |
| 0x80–bc | Current record; reads never advance the queue |
| 0x100–13c | Atomic 16-word snapshot |

Status bits 0–8: visit present, source closed, engine busy, queue nonempty,
settled, partial final window, faulted, aborted visit, settled and drained.
Fault bits 0–5: cadence, engine/rejected arm, source abort, invalid MMIO write,
counter exhaustion, accounting inconsistency. Unsupported writes, partial
strobes and POP on an empty queue are faults. Reserved reads return zero.

Snapshot words are status, faults, queue count, high water, buffered, popped,
opportunities, admitted, skipped, completed, supported, aborted, outstanding,
visit, first source low, first source high. Snapshot generation advances on
each latch and wraps from `0xffffffff` to 1. Counters do not silently wrap.

Source close drains complete windows. A partial final capture or explicit abort
cancels unfinished arithmetic while preserving queued evidence and counters.
Closure requires opportunities = admitted + skipped, admitted = completed +
aborted, zero outstanding work and all queued records popped. An aborted window
may retain candidate evidence without a final decision; it is not a negative
detection. CLEAR starts a new visit only after ownership has been released.

Linux exposes `local_search_abi`, `local_search_snapshot`,
`local_search_baseline_snapshot` and `local_search_final_snapshot` on the IQ
device. Search snapshot text is `GLA1 00010000 GENERATION 2500000 250000 14000`
followed by 16 eight-digit hexadecimal words. Base IQ and source closure
snapshots retain their existing layouts with distinct GLA1 magic. Their shared
generation binds that pair; the local snapshot has its own generation and is
bound by visit and settled source coordinates.

`starlink_glrt_local_abi.attest_capture` checks source closure, exact IQ byte
count, local counts, CPU transfer deltas, record order, window support and
winning-candidate correspondence. It returns only completed windows for host
comparison. RF identity and numerical equivalence are separate release gates.

## Reproducible predeployment checks

`starlink_glrt_local_replay.py --queued` runs the complete grid on pinned saved
IQ, through real cadence/MMIO/FIFO RTL with the host reader delayed 250 ms.
It compares every record with the independent integer model. No radio is used.

`python -m tools.starlink_glrt_capture --local-search` records GLA1 IQ and events
using the existing bounded capture lifecycle. It requires direct 2.5 MS/s,
rejects legacy threshold/profile overrides, enables the event consumer before
IQ and keeps it running through stop/drain. It persists both baseline/final
local search snapshots and attests the exact saved IQ windows. The command
requires an already configured and authorized radio; it does not tune or flash.
Its schema is `starlink-glrt-local-iio-capture/v1`. Successful transport does not
set `independent_host_glrt_run` or `live_detector_qualified` to true.

`starlink_glrt_local_search_ooc.tcl OUTPUT ROMS --control-netlist` produces a
linked, unplaced component with its source hashes. The board build consumes it
with `scripts/build_glrt_board.sh 2500000 OUTPUT --local-search NETLIST`.
This component has no fixture registers or exported timing exceptions. Full
board route, CDC, calibration, firmware packaging, PPU deployment and matched
physical capture remain required before deployment verification is complete.
