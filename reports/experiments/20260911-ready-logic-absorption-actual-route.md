# READY logic absorption: measured improvement, timing still fails

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-ready-logic-absorption`.
FW `e63d319578c46f4b186b5feda949676ff4234c97`;
HDL `17092c6efad24aa41d6928b5440bb696251fcce2`.

Exactly two KEEP attributes are removed from the parallel capacity and kernel
input-room wires. Equations, state, arithmetic, guard wiring, clocks, exceptions,
actual-FFT stimuli and synthesis recipe are unchanged. Source inverse and
mutation tests enforce that bounded delta. No hardware was accessed.

## Results

992 regression tests pass. Both actual generated-FFT campaigns pass with all
64,512 numerical records and CSV bytes identical to the parent. Service remains
`3663/3663/4929/11729/3663/3663` clocks; READY witnesses cover 503,564 main and
437,625 auxiliary observations. Synthesis and routing use the same frozen source.

| Metric | Parallel READY parent | KEEP removal |
| --- | ---: | ---: |
| Global WNS (ns) | -1.434 | -1.245 |
| Same 175 MHz domain WNS (ns) | -1.434 | -1.046 |
| TNS (ns) | -302.161 | -245.991 |
| Failing setup endpoints | 590 | 453 |
| LUT / FF | 2729 / 5788 | 2728 / 5790 |

All 8458 nets route without errors. Hold +0.077 ns and pulse +1.830 ns pass;
21 DSP and 15 RAMB18 remain. The original worst release-to-kernel-protocol-fault
path improves to -0.733 ns, still failing. The release register is no longer
replicated; a read-only query covers every original/replica register, not just
the old name. Other release paths remain: fast-fault -0.881, ROM-valid -0.739,
output-request -0.696 ns.

The same-domain worst now goes from return exponent bit 1 through handoff
identity and completion/current-fault/commit logic to the forward guard's
awaiting-ACK register: eight logic levels, 6.705 ns data delay, 77.5% routing.
The neighboring product-position-to-guard-state path is -1.045 ns. Global worst
is output metadata bit 27 crossing 175 to 100 MHz. Reset first-stage fanout and
registered-purge structure checks pass. CDC remains nine CDC-3 and 208 CDC-15
items, with no waivers. All 114/124 OOC input/output ports remain unqualified.

## Decision and path forward

Retain as an improved development reference, not a release. Next examine the
held handoff-identity to final commit/ACK dependency as one control boundary.
An earlier completion snapshot alone does not cut the separate guard's live
fault/commit path. Any staged decision must bind its descriptor, bank and epoch,
retain immediate reset/fault cancellation, and reject stale or changed evidence
before publication or ACK. Test late faults, expiry, stalls and reset, then
repeat the actual FFT and unchanged-constraint route. More TX removal does not
address these measured control dependencies.

Bundled-data CDC qualification and full receiver timing at real board clocks
remain separate gates. Preserve native 60 MS/s fine search and the independent
2.5 MS/s CI16 IIO stream. Actual 60 MS/s RX calibration, continuous reception,
sustained Ethernet/IIO, blind GLRT comparison, 120 ms dwells and 300 s scans
must pass before a pinned PPU/rollback package goes to `.18`, then `.17` over
Ethernet. `.20/.21` are excluded. No PPU/main or primary HDL gitlink changes.

## Evidence

[Read-back-verified archive](20260911-ready-logic-absorption-evidence.tgz),
[receipt](20260911-ready-logic-absorption-evidence.json):
33,404,884 bytes, 6267 members, SHA256
`cc9b2a76a3626eaa1a50135e786d9ba40a937d1b02adffa865c460ec67da95e7`.
Includes frozen sources, actual FFT logs/CSV, synthesis/routed checkpoints,
tests, path/CDC reports and the parent source/timing reference.
Raw evidence: `/dev/shm/starlink-ready-absorption.QxP2Z5AO`.
Prepared SHA: `9f97603c784ee7be2e7c4bd005bb5b2f4c4c018bdd97f9dbb674f9e18ba6bcae`.
Routed DCP SHA: `9c2fb242c47bf39a0698eddf86667f97657e8a5646238e0031125e83000930aa`.
Parent: [parallel READY integration](20260911-parallel-kernel-ready-actual-route.md).
