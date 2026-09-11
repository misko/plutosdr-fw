# Private quarantine offer: local improvement, no overall promotion

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-private-quarantine-offer`.
FW `212da887106bbebdf20eb08bfe80661dc3e2d46e`;
HDL `f0cedf13dfe0cbd6f0b4a5e309ad95d47b53d418`. Both are pushed.

## Outcome

The inverse guard's private-write offer now optionally uses raw private
occupancy rather than sticky-fault-masked validity. Public valid/commit/ACK,
admission and diagnostics remain unchanged under identical guard inputs.
An extra write may occur only into unpublished, explicitly committed storage
after quarantine; it is not publication authority. Common epoch reset is still
required before reuse. Default callers and the forward guard are unchanged.
Two of 22 runtime modules change; no new state, latency, arithmetic or RAM.

Both actual FFT campaigns pass, all **64512 numerical records and CSV bytes
remain identical**, and service stays `3663/3663/4929/11729/3663/3663` clocks.
Main and auxiliary monitors observe one and two private-only differing cycles,
respectively, each with known sticky fault and no public valid, commit, replay
acceptance, ACK or new admission. Existing recovery tests pass.

**843 regression + ten new evidence tests pass (853 distinct).** Component
coverage includes a separate parent guard, 8644 checks/mode, 32 directed
fault/recovery jobs, randomized traffic, four-state algebra, invalid modes and
unsafe mutants. The component/lint subset is 13 tests; the 17-test evidence run
includes seven overlapping archive tests. The first full regression had one
historical source-inventory mismatch (837 pass); the exact inverse was updated
and the fresh full run passed. No runtime change occurred during actual runs.
This is bounded simulation, not universal formal or continuous-RX proof.

## Timing: mixed result, not closed

| Metric | Quiet-fence reference | Private-offer candidate |
| --- | ---: | ---: |
| WNS, ns | -1.241 | -1.322 |
| TNS, ns | -274.139 | -323.338 |
| Setup failing endpoints | 572 | 622 |
| Inverse guard bit-3 fault to commit, ns | -1.235 | -0.292 |
| Same source to fast fault, ns | -1.228 | -0.444 |
| LUT / FF | 2825 / 5796 | 2808 / 5796 |

The queried guard source to output publication request is -0.054 ns. All three
targeted paths remain negative; no path closure is claimed. Overall setup
regresses, so **the quiet-fence parent remains the better routed reference**.
Keep this branch as evidence of the local improvement, not a receiver promotion.

New worst: product-bank held metadata bit 34 through preflight identity into
fast fault, eight logic levels, 6.984 ns data delay (5.536 ns routing). A nearby
reset-readiness-to-kernel-ROM-valid path is -1.318 ns. Route has 8460 fully routed
nets, zero routing errors, passing hold (+0.071 ns) and pulse (1.830 ns), 21 DSP
and 15 RAMB18. Original 100/175 MHz OOC clocks, recipe and exceptions unchanged.

Reset structure remains clean. CDC inventory remains nine CDC-3 information
items and 208 CDC-15 warnings. 114 inputs and 124 outputs remain unconstrained
in OOC; no full receiver or deployment signoff.

## Next steps and release scope

Investigate preflight identity and reset-to-ROM-valid cones before another
change. Any held-lease certificate/private validation stage must preserve
current admission/cancellation and account for an old output being read during
new-job preflight. Do not simply delay a fault or authorize from stale metadata.
Repeat the actual FFT and route gates; qualify metadata CDC separately with
justified ownership and physical bounds, not broad waivers.

Native 60 MS/s fine search and 2.5 MS/s CI16 IIO inspection remain required.
Still outstanding: full receiver integration/timing/CDC/board clocks, continuous
RX, actual 60 MS/s calibration, sustained Ethernet/IIO, blind host GLRT, 120 ms
dwells and 300 s scans; then pinned PPU package/rollback, .18 canary and .17
Ethernet-only deployment. No radios, PPU/main, primary receiver HDL or TX removal.

## Evidence and recovery

[Archive](20260911-private-quarantine-offer-evidence.tgz),
[verified read-back](20260911-private-quarantine-offer-evidence.json):
39,538,985 bytes / 11047 members, SHA256
`59a029c7d6cb7c1cd6ffe1bc2e28e4e0ef19ef34eef33062c06a21680348b915`.
Includes frozen sources, actual logs/CSV, synthesized/routed checkpoints,
failed and corrected regression evidence, inspections and parent source.
Raw evidence remains at `/dev/shm/starlink-private-quarantine.tu8FkVR0`.

Prepared: `2f518556a5e04dc9e161aff35d3c079914a1ecb9d6d7ffb1c6d8064b5337fb25`.
Routed DCP: `b31f03b331729ee00058e17169667ac8fffd84a161c62fe32848cb1d00aa7faf`.
Parent: [quiet publication fence](20260911-replay-quiet-fence-actual-route.md).
Full implementation notes are in the experimental branch's
`docs/starlink-private-quarantine-offer-20260911.md`.

Disk housekeeping made only clean, inactive FW worktrees sparse for duplicate
committed reports: balanced handoff, reset CDC, quiet fence, quiet contract,
split-output metadata and output CDC contract. Those reports remain recoverable
from Git; their HDL, raw evidence and primary reports were not removed.
