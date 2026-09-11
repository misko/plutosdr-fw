# Completion receipt integrated with actual FFT: setup remains open

DO NOT MERGE or deploy this candidate.
FW/HDL branch: `codex/starlink-rx-only-do-not-merge-completion-mailbox-stage`.
FW `14af35ec6`, HDL `cbb36f3b6`.

The isolated subsystem now places a one-entry completion receipt before the
output publication sequencer. Acceptance immediately reserves the actual bank
and freezes the accepted payload; the sequencer starts COMMIT one clock later.
Actual bank publication and reader ACK remain mandatory. Current fault vetoes,
arithmetic, buffers and clocks are unchanged. No further features or TX removal.

## Tested result

- 720 regression tests pass. After correcting three old phase-based ownership
  monitor predicates to include pending ownership, 40 focused tests pass.
  All 22 runtime modules are byte-identical across that monitor correction.
- Eleven new evidence tests pass (731 distinct regression/new-evidence tests),
  plus seven overlapping archive tests. Invalid or missing actual receipt
  coverage blocks route.
- Successful actual FFT main and auxiliary runs: **207.77 s / 145.38 s**.
  All **64512 indexed numerical comparisons** pass. The CSV byte order changes;
  no parent byte-identity claim is made.
- Service is **3663/3663/4929/11729/3663/3663 clocks**: one extra normal clock.
  New pending-boundary tests cover vendor fault, raw reset and FFT reset, each
  followed by a fresh 512-word, one-release recovery. Existing boundary tests
  remain. This is not continuous 60 MS/s receiver or 750 measurements/s proof.
- Retained diagnostics include rejected V1 monitor runs and a V2 main whose
  launcher exited 143 without an outcome record despite simulator/Tcl success.
  The cause is unknown. Only the fresh V3 successful source-bound outcome was
  admitted to route. The failed record audit is preserved, not reclassified.

## Routed result

Unchanged 100/175 MHz OOC recipe; route takes 49.63 s.
The exact old `output_descriptor_payload_reg[4]/C` to
`output_control/phase_reg[0]/D` combinational path is absent. From the same
source, new `complete_pending` setup is **+0.096 ns**, while `publication_seen`
still has **−0.008 ns** slack. No constraints changed.

Whole-subsystem **WNS −1.560 ns / TNS −479.076 ns / 837 failing endpoints**.
Parent: −1.736 ns / −430.075 ns / 715 failures. Better worst slack but worse
total negative slack and endpoint count: this is **not timing closure**.

The new worst same-domain path is `slow_reset_fast_reg[1]/C` to
`admission_gate/snapshot_good_reg[0]/R`: nine logic levels, 6.666 ns data delay,
5.094 ns routing. It crosses epoch/reset qualification, product readiness and
completion/admission control. It must not be waived as an asynchronous reset.

8405 nets route with zero errors; hold +0.071 ns and pulse +1.830 ns pass.
2760 LUTs, 5790 registers, 21 DSPs, 15 RAMB18s. Reset inspection retains exclusive
first-to-second-stage fanout and registered purge signaling. Nine CDC-3 info
and 208 CDC-15 bundled-data warnings remain; no CDC-1/CDC-10 critical findings.
114 inputs / 124 outputs remain unconstrained in OOC; no full-board signoff.

## Next gate

Keep this candidate and its parent for comparison; do not promote or add
features. Next isolate private admission-snapshot housekeeping from the long
reset/readiness/current-fault chain, without delaying public cancellation or
exposing stale payloads. Prove ownership/fault/reset behavior before another
actual FFT and unchanged-constraint route. Keep the publication-seen endpoint
in that audit. Bundled-data timing qualification remains separate.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection are not
removed. Full receiver timing/CDC/reset, board clocks, actual 60 MS/s RX
calibration and sustained IIO/Ethernet precede reversible `.18` canary then
`.17` PPU Ethernet-only deployment, pinned rollback, 120 ms valid dwells,
300 s scans and blind host GLRT. No radio, PPU/main or primary HDL changed.

## Preserved evidence

[Archive](20260911-completion-mailbox-stage-evidence.tgz),
[readback receipt](20260911-completion-mailbox-stage-evidence.json):
**44386030 bytes / 5939 verified members**, SHA256
`d427aae630ae502d6891f5d557b9717bbcf759dd512cea82696bf442afc2d2bf`.
Contains source snapshots, rejected/incomplete diagnostics, successful actual
CSV/logs, synthesis/routed checkpoints, tests, inspections and implementation
notes. Duplicate regression CSV/DCP files are excluded; identical vendor VHDL
is kept once after equality verification. No raw evidence deleted.

Prepared V2: `579b4b69fee7eb67a20befbb901d53b0ff033dd7305603e57b532d950d47114c`.
Routed DCP: `0a25faf068b197ffa2daa6d24f548a4bf446e32b38642c36ce71bda9deed35b5`.
Parent: [balanced handoff route](20260911-balanced-handoff-actual-route.md).
