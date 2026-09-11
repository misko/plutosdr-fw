# READY logic absorption — DO NOT MERGE

Remove exactly two KEEP attributes, on `forward_parallel_capacity` and
`parallel_input_room`. No equations, state, arithmetic, clocks, timing exceptions,
parameters, test stimuli or synthesis recipe change. The actual FFT, original
buffers and guards remain integrated. Source inverse tests reject behavioral
changes and reconstruct the parent by restoring these two attributes.

## Measured outcome

992 regression tests pass, including the four-state and evidence checks from
the preceding experiment. Both actual generated-FFT campaigns pass with 64,512
identical numerical records and unchanged service clocks:
`3663/3663/4929/11729/3663/3663`. The READY witnesses cover 503,564 main and
437,625 auxiliary observations. Source-matched synthesis and routing complete.

| Metric | Parallel READY parent | Two KEEP attributes removed |
| --- | ---: | ---: |
| Global WNS (ns) | -1.434 | -1.245 |
| Same 175 MHz domain WNS (ns) | -1.434 | -1.046 |
| TNS (ns) | -302.161 | -245.991 |
| Failing setup endpoints | 590 | 453 |
| LUT / FF | 2729 / 5788 | 2728 / 5790 |

This is a useful improvement in this matched route, not timing closure or a
general guarantee about KEEP attributes. All 8458 nets route without errors;
hold +0.077 ns and pulse +1.830 ns pass. DSP/RAMB18 remain 21/15.
The OOC 114 inputs and 124 outputs remain unqualified.

The release register is no longer replicated. A read-only inspection queries
all matching release registers (including any replicas), not just the original.
Release-to-kernel-protocol-fault improves from -1.434 to -0.733 ns, but remains
failing. Release-to-fast-fault is -0.881, ROM-valid -0.739 and output-request
-0.696 ns. No path-removal claim is made.

The new same-domain worst is return exponent bit 1 through handoff identity,
completion/current-fault and commit/ACK logic to the forward guard's awaiting-ACK
register: eight logic levels, 6.705 ns data delay, 77.5% routing. The adjacent
product-position-to-guard-state path is -1.045 ns. These are control-path
dependencies, not evidence that the FFT arithmetic or TX is the bottleneck.
Global worst is a held output metadata bit crossing 175 to 100 MHz. Reset
first-stage fanout and registered-purge structural checks pass; CDC remains
nine CDC-3 and 208 CDC-15 items, without waivers or qualification.

## Next implementation boundary

Keep this candidate as a measured development reference, not a release.
Inspect the held forward-handoff identity and final commit/ACK dependency
together. A staged decision must bind the owning descriptor, bank and epoch,
retain immediate reset/fault cancellation, and reject changed or expired facts
before public publication or ACK. Existing completion snapshots do not by
themselves sever the separate guard's current-fault/commit path. Any register
added there must be tested for stale evidence, late faults, backpressure and
reset before repeating the actual FFT and route campaign. Do not simply delay
the fault veto or lower the clock to turn this result green.

Qualify the bundled-data clock crossings independently; this route has not
proved their board-level capture constraints. Then integrate and close the
full receiver at real board clocks, retaining native 60 MS/s fine search and
the independent 2.5 MS/s CI16 IIO stream. Continuous RX, actual 60 MS/s RX
calibration, sustained Ethernet/IIO, blind GLRT comparison, 120 ms dwells and
300 s scans remain deployment gates. A pinned PPU/rollback package goes to
`.18` first, then `.17` Ethernet-only. No radio, PPU/main, primary HDL gitlink
or TX functionality is changed here; `.20/.21` remain excluded.

Raw evidence: `/dev/shm/starlink-ready-absorption.QxP2Z5AO`.
Prepared SHA: `9f97603c784ee7be2e7c4bd005bb5b2f4c4c018bdd97f9dbb674f9e18ba6bcae`.
Routed DCP SHA: `9c2fb242c47bf39a0698eddf86667f97657e8a5646238e0031125e83000930aa`.
`tools/record_ready_absorption_evidence.py` re-audits the frozen actual evidence,
source delta, route and read-only inspections and read-back verifies the archive.
