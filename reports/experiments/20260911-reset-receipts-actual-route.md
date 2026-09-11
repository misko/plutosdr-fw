# Reset receipts: critical control CDC findings removed, setup still fails

DO NOT MERGE or deploy this subsystem candidate.
FW/HDL branch: `codex/starlink-rx-only-do-not-merge-reset-cdc`.
FW `fd2174c3a`, HDL `cf14f5d2d`.

## Completed

The actual FFT subsystem now uses local reset-applied receipts for its source
and output mailboxes, rather than reading first-stage synchronizer taps from
reset-purge logic. The slow-purge indication is registered before crossing.
All arithmetic, buffer data paths, framing/publication checks and real ACK
remain unchanged. The same-domain product mailbox is unchanged.

- **670 regression + seven new evidence tests pass** (677 distinct in these
  suites). Twelve clock/phase runs cover 156 complete blocks and 120 reset
  cases, including release of raw reset while a domain clock remains stopped.
- Both actual FFT campaigns pass: main 196.67 s; auxiliary 129.27 s.
  **64512 indexed numerical records are exact**. CSV order changes at 2288
  row positions with reset phase; this is not a byte-identical CSV claim.
  Service remains 3662/3662/4929/11729/3662/3662 clocks.
- Synthesis 99.14 s; unchanged-constraint route 49.32 s.
- Routed inspection confirms all four source/output request/ACK first-stage
  outputs feed only their second stages. Purge crosses directly from a register.
  **Four CDC-1 and one CDC-10 critical findings are removed.** Nine CDC-3
  informational synchronizers and **208 CDC-15 bundled-data warnings** remain.

## Still not deployable

| Measurement | Parent | Reset receipts |
|---|---:|---:|
| Worst setup slack | −1.258 ns | **−1.496 ns** |
| Same-domain fast-clock slack | −1.215 ns | **−1.370 ns** |
| Total negative slack | −328.306 ns | **−436.221 ns** |
| Failing endpoints | 692 | 675 |

This is a verified reset/CDC structural improvement, **not a timing improvement**.
All 8384 nets route without errors; hold/pulse pass. 2740 LUTs, 5790 registers,
21 DSPs, 15 RAMB18s. OOC still has 114 inputs and 124 outputs unconstrained.
Output metadata's 37 paths measure 0.619–1.237 ns. No timing exceptions changed.
Zero critical findings in this OOC CDC report is not full receiver/board or
analog metastability qualification.

Worst same-domain path is now forward `return_exponent_reg[2]` through product
handoff identity/current fault logic to `output_bank/request_toggle_reg/D`:
12 logic levels, 6.919 ns data delay, 4.617 ns routing. Next investigate that
wide identity/publication path while preserving current fault vetoes and actual
FFT return capacity. Separately qualify narrowly scoped bundled-data bounds.
Do not assume the earlier output equality is still the worst path.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
unchanged. Full receiver timing/CDC, board clocks, native RX calibration and
sustained Ethernet/IIO remain before reversible `.18` canary and `.17` PPU
Ethernet-only deployment with pinned rollback, 120 ms valid dwells, 300 s scans
and blind host GLRT. No radios, PPU/main or primary production HDL changes.

## Preserved evidence

[Archive](20260911-reset-receipts-evidence.tgz) and
[readback receipt](20260911-reset-receipts-evidence.json): 54943996 bytes,
5517 verified members, SHA256
`2abb39c8ae40a95a67e89936f37a40d4a80b583b5b3432f01a84ff0cd22fd01b`.
Includes frozen sources, actual numerical results, checkpoints, tests and
inspection reports, plus the detailed implementation document.

Prepared SHA: `28b4f9dbf7e61175b9dba8b87136438f6a134b88f111f0afb23e03ea344c736a`.
Routed DCP SHA: `6ac76c672827b6b227db586d316bf81921241cb6d15debd540f132c9ee6ee741`.
Large inherited regression-only copied/mutated CSVs and DCPs are excluded from
the Git-sized archive; actual campaign CSVs and synthesis/routed DCPs are
included. The original full archive and all raw files remain in task RAM.
The focused preflight inventory correction and packaging details are documented
inside the archive. Parent dependency: [CDC contract](20260911-output-cdc-contract.md)
and [previous actual route](20260911-staged-outputmetadata-actual-route.md).
