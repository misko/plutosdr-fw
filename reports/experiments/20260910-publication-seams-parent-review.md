# Product integration seams: independent full gate

Parent original97763 exits0: **2752 PASS in78.61s**, comprising1308 additive
tests and the unchanged1444 baseline. All154 captured source files match before
and after. This clears the primitive-interface gate for additive P1 controller
implementation, not actual FFT, physical timing or receiver deployment.

Tested owner commits: FW`eba403dc38b7a0d5a5634a4f76cb0bf78a3d7ae9`,
HDL`1703e90347b607219d9c714c2cce698deea6ab9d`. The parent launch began before
these commits were recorded; exact file hashes, not its earlier HEAD labels,
identify the test inputs. Final test SHA256:
`db0d31b2e1b8f200887361bfc4044c04eb0759111fb9f5b4ae286991752d1374`.

## What passed

- Sampled arithmetic READY is distinct from advertised bank capacity. Interior
  and final holds, unknown controls, raw closed offers and the issuer-Q-only
  invalid-caller capacity gap are exercised. Private take requires both READY
  and capacity; raw VALID observation remains ungated.
- Publication-only faults immediately veto seal/publication and retain the
  existing reason category. They do not directly gate reader VALID, certificate
  acceptance or release. The caller separately protects the actual result-guard
  ACK; a missing caller-fence mutant is rejected.
- All eight fault categories with1/X/Z values, fault-edge reading, certificate
  and release behavior, pre-armed observation window, one-sided resets and
  next-edge quarantine are checked. Parent separately verifies96 logged exact
  reason/read-count rows: seal/pub read0, read-edge read1, release-edge read512.
- Disabled hostile new inputs preserve the old path. Whole-source inverse
  patches recover the canonical bank and reviewed issuer, and exact register
  declarations remain unchanged. No new primitive state, RAM or DSP is declared.
- Eight healthy enabled and disabled leases have identical full job/latency
  records:512 words, no input holes,1555 actor clocks admission-to-release.
  This is not the real P1 controller's service interval.
- The real consumer certificate coupling case is specifically a checked input
  beat (`received=2`), not a naturally reachable full-P1 closed-phase proof.

Parent read the complete final suite, bank bench, interface include and both
inverse patches. Independent reviewer checked the same source and final
receipt/alias correction. Missing READY/capacity/raw observation, unknown-ready
diagnostic, seal/pub/reason/internal-update and caller-ACK mutants fail at their
intended boundaries. Tests also reject invalid options and malformed success
receipts. Old cases and numerical expectations were not weakened.

## Structural evidence and preserved failures

Fresh parent netlist:3488 continuous nodes, including38LS nodes, no cycle.
All three restored publication backedges produce cycles. An independent
scope-aware traversal checks actual net-driver identities: seal/pub depend on
the publication bus; seven read/certificate/release/capacity sinks do not.
These are continuous-graph properties, not routed timing or reachability.

Owner original14624 remains **2749 PASS / 1 FAIL**. Its positive dependency
test compared named alias IDs, while compiled consumers referenced the driver's
ID directly. The earlier negative alias exclusions were therefore insufficient
too. The correction resolves only immediate drivers and adds connected and
disconnected controls; the disconnected case deliberately shares upstream
state. Neither parser nor RTL changed. Older product-metadata exclusions
already used driver identities and are not invalidated by this new test bug.
The failed run's log/XML are included; its full original recovery remains intact.

Parent's first preparation stopped at its hash guard before pytest because
the owner's final alias-control refinement landed concurrently. Parent read
and pinned the final change before launching97763. Its first independent audit
stopped at case-path discovery because pytest shortened directory names; only
that glob changed. Both failed preparation/audit scripts and receipts remain.

## Evidence and next action

Parent audit verifies80 case manifests/804 source entries, XML counts and exact
healthy/fault records. Archive includes all154 source snapshots, compiled case
sources/VVPs/logs, XML, parent audit and preserved early attempts. Only pytest
`current` convenience symlinks are excluded.

Archive `20260910-publication-seams-parent.tgz`:7237865 bytes, SHA256
`f8b164259c822be63f3cf77a507f3e9cd7d642ed87c774dcea074e7e49c30e8c`;
archive comparison exits0. XML SHA256:
`71d3a10e26db39aaff201f7638b6dc5696f211284854b2f25da51d35f168dd84`.
Audit SHA256:
`8db839b8c87d2df064e9c509913520113cc610f052438be8f819fdf7d220e0e5`.
Recovery `publication-seams-parent.e3uk9SFG` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

Next authorized work: additive P1 integration with independent forward-origin
lease/head binding at ACK and inverse start; exact sampled READY; separated
publication/current-ACK protections; persistent handoff receipt; and the
peer-purge barrier covering source reader and source-fault sampling. Preserve
literal disabled behavior and canonical sources. Bounded healthy/fault/reset/
graph integration tests precede source-specific actual-core preparation.

No production HDL gitlink, PPU source or radio changed. The canonical15MS/s
coarse/original-rate fine path,2.5MS/s IIO evidence,120ms/300s scanner, full
receiver routing/calibration and `.18`→`.17` deployment gates remain required.
