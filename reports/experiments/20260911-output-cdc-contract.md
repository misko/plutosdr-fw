# Output metadata CDC contract: passing digital tests, structural gate open

DO NOT MERGE firmware into main. Diagnostic branch:
`codex/starlink-rx-only-do-not-merge-output-cdc-contract`.
Diagnostic FW commit: `7a686d74f` (pushed to that branch).
Runtime remains parent FW `b1871495e36dfee3c45d2d2fa6a23a95b5a57179`,
HDL `7a2a271eaddcdaa95214b16fab0b89fbc414407a`, unchanged.

The simpler controller is already integrated with the actual FFT and buffers.
This checkpoint adds read-only inspection and tests, not another RTL revision,
timing exception, route or deployment. The parent actual-FFT numerical evidence
and failing route remain the reference.

## Verified result

- 17 digital contract tests pass: twelve clock/phase profiles and four unsafe
  mutations plus source identity. Across the positive runs, 156 complete reader
  blocks and 120 reset cases pass, including stopped clocks, both raw resets,
  unread ownership, partial transfers, changing next metadata and fresh recovery.
- 12 assessment tests and seven archive tests pass. These are 36 tests executed
  for this checkpoint, not a new execution of the parent's 652-test suite.
- The pinned routed checkpoint has all 37 same-bit metadata paths, with data
  delays of 0.737–1.158 ns. At 175-to-100 MHz, observed minimum publication-to-
  capture is 20.035 ns, consistent with the conditional two-reader-period
  digital bound. Digital simulation does not model analog metastability.
- All four source/output request/ACK first-stage synchronizer registers also
  feed epoch purge counters. Their reset-idle predicates inspect the entire
  two-stage vectors. Vivado reports four CDC-1 critical findings and one CDC-10
  on the combinational slow-purge indication.

The latter is a structural qualification issue, not observed data corruption.
The assessment deliberately keeps `control_structure_qualified`,
`constraint_change_authorized` and `deployment_eligible` false.

A final combined rerun passes **36 tests in 1.52 s**, with unchanged sources.
An initial rerun using the default temporary directory failed before Verilog
elaboration (`ivlpp: No input files given`); setting `TMPDIR` to the existing
task-local RAM directory restores compilation. The precise default-directory
failure cause has not been established. It is not counted as an RTL result.
For reproduction, use a fresh pytest basetemp, set
`TMPDIR=/dev/shm/starlink-output-cdc.JIdEms`, and unset `PYTHONHOME`,
`PYTHONPATH`, `PYTHONOPTIMIZE` and `LD_LIBRARY_PATH`. Evidence tests also require
the pinned parent snapshot/checkpoint paths documented in the archived sources.

## Timing and next implementation

Parent timing remains **−1.258 ns WNS / −328.306 ns TNS / 692 failing endpoints**.
The worst same-domain 175 MHz path is **−1.215 ns**. The worst overall metadata
CDC path is analyzed with a 0.002 ns adjacent-edge relationship, whereas the
mailbox waits for synchronized publication before capture. This distinction
does not authorize hiding the crossing or declaring timing closed.

1. Replace first-stage reset observations with locally justified reset/idle
   receipts. Preserve purge duration, both-reset and stopped-clock behavior;
   do not simply remove the existing checks.
2. Register the slow-purge indication before synchronization and account for
   the added startup cycle. Repeat actual FFT, reset, route and CDC checks.
3. Only after qualification, derive narrowly scoped bundled-data constraints.
   A 10 ns output datapath bound is a proposal, not applied or approved here.
   Other bundles require separate review; no blanket false paths/clock groups.
4. Address the remaining same-domain output-validation path independently.

Native 60 MS/s fine search and the independent 2.5 MS/s CI16 IIO inspection
stream remain unchanged. No radio, PPU/main or primary production HDL changes.
Full receiver timing/CDC, board clocks, native RX calibration and sustained
Ethernet/IIO still precede reversible `.18` canary and `.17` PPU Ethernet-only
deployment, with pinned rollback, 120 ms valid dwells, 300 s scans and blind
host GLRT comparison. No deployment ETA is established by this OOC result.

## Evidence

Archive: [CDC contract evidence](20260911-output-cdc-contract-evidence.tgz).
[Readback receipt](20260911-output-cdc-contract-evidence.json): 233711 bytes,
795 verified members, SHA256
`9530567a03943824b4af3c0d2228d19eac5a8025754712953d0b76d152230659`.
Includes exact tests, routed inspection reports, per-bit paths, assessment and
the detailed contract document. Parent archive is an explicit dependency,
SHA256 `7b3909f3b4737d226741d9a5675eec6c6114ec81ec464d31c6dd91d993a8c6f4`.
See [parent actual FFT and route](20260911-staged-outputmetadata-actual-route.md).
