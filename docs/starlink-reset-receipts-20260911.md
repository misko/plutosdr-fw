# Local reset receipts integrated with actual FFT — DO NOT MERGE

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-reset-cdc`.
Parent FW `7a686d74fb629c5292a80812a54add00f3c41e6b`, HDL
`7a2a271eaddcdaa95214b16fab0b89fbc414407a`.

## Implementation

Source/output mailbox reset observations now require a local clocked
`reset_applied` receipt, local running=false, the settled second synchronizer
stage and all original local ownership/cursor/fault idle predicates. First
synchronizer stages feed only their second stages. A local edge while reset is
active clears both synchronizer stages and sets the receipt together; this is
not a claim that an unclocked domain has reset. The common barrier still needs
two local idle observations and coordinated cross-domain release.

The slow-purge counter remains saturating at two. Its equality result sets a
registered monotonic flag, which then crosses the existing two-stage
synchronizer. This adds one slow-domain startup cycle, not a datapath pipeline
stage. Either raw reset cancels the flag asynchronously. No private core reset
is connected to the outer epoch.

Three explicit experimental variants replace the source mailbox, output mailbox
and barrier in the staged top. The product mailbox is unchanged (same domain).
All 22 compiled runtime modules are source pinned. Tests invert the exact
mailbox/top/barrier delta and prove every other runtime source unchanged.
FFT arithmetic, buffer data paths, current framing/publication checks and real
reader ACK remain unchanged; the prior modules remain as the reference.

## Executed verification

- **670 regression tests pass in 83.29 s**: 652 inherited plus 18 new tests.
  New bounded mailbox/barrier campaigns cover twelve clock/phase combinations,
  156 complete reader blocks, 120 reset cases, and four unsafe data mutations.
  Reset cases now release raw reset while the writer or reader clock remains
  stopped, require both domains to stay fenced, then verify fresh recovery.
- **Seven new evidence tests pass**, plus seven overlapping archive tests,
  in 1.46 s. Missing terminal evidence, extra first-stage fanout, critical CDC,
  applied constraints and false timing claims are rejected. Distinct total 677.
- Main actual FFT: **196.67 s**, all **64512 indexed numerical records exact**.
  Service remains **3662/3662/4929/11729/3662/3662 clocks**. CSV bytes differ
  because 2288 chronological row positions move with reset phase; the complete
  record multiset and independent seven-stream reference comparison are exact.
- Auxiliary actual FFT: **129.27 s**, all inherited six output corruption/reset,
  six ACK, twelve forward-receipt and twelve product-stage boundaries pass.
  Main stopped-reader reset cases purge six slow edges and recover 512 reads.
- Synthesis **99.14 s**, route **49.32 s**. Both actual campaigns and synthesis
  use the same frozen prepared SHA. The route gate re-audits both campaigns.

An initial focused preflight had 67 passes and one source-inventory failure:
the historical unchanged-source list did not recognize the three named variants.
Adding them to the explicit delta list, backed by the new exact-delta tests,
resolves that test bookkeeping issue. The complete 670-test run is after this
correction. No runtime/bench corrections occurred after the frozen preparation.

## Physical result

Read-only inspection of the routed checkpoint confirms all four source/output
request/ACK first-stage outputs have exactly one endpoint: their second-stage D.
Both stages retain ASYNC_REG. The purge flag's Q net directly feeds its first
synchronizer D, without combinational logic.

The prior **four CDC-1 and one CDC-10 critical findings are gone**. Vivado now
reports nine CDC-3 informational synchronizers and **208 CDC-15 bundled-data
warnings**. This closes the identified control-structure defect, not all CDC
qualification: unconstrained input ports are outside this OOC CDC analysis,
and analog metastability/MTBF, full receiver reset and board clocks are unproven.

All 37 output metadata paths remain visible and measured, **0.619–1.237 ns**.
No timing exceptions or constraints were changed. The source-derived conditional
hold/capture contract remains applicable, but no blanket false path or automatic
10 ns constraint authorization is asserted here.

| Routed measurement | Parent | Reset receipts |
|---|---:|---:|
| Worst setup slack | −1.258 ns | **−1.496 ns** |
| Same-domain 175 MHz slack | −1.215 ns | **−1.370 ns** |
| Total negative slack | −328.306 ns | **−436.221 ns** |
| Failing endpoints | 692 | 675 |
| LUT / FF | 2747 / 5793 | 2740 / 5790 |

All 8384 nets route, no routing errors. Hold +0.058 ns and pulse +1.830 ns pass.
21 DSPs and 15 RAMB18s, with 114 inputs/124 outputs unconstrained in OOC.
This route is **not timing closure and not a timing improvement**.

Worst overall remains metadata CDC (bit 36). The worst same-domain path now
starts at `owners[0].result_guard/return_exponent_reg[2]`, traverses product
handoff identity and current fault/publication logic, and ends at
`output_bank/request_toggle_reg/D`: 12 logic levels, 6.919 ns data delay,
4.617 ns routing. The remaining timing work must follow this measured path,
not assume the previous output equality remains the worst path.

## Next gate and deployment

1. Retain the reset-safe structure; investigate the wide product handoff identity
   check/current publication fan-in. Any precomputed identity must refer to the
   actual captured descriptor, preserve expiry/reset and current fault vetoes,
   and fit actual FFT return buffering. Repeat numerical/service/reset/route
   evidence before choosing a new implementation.
2. Separately derive narrowly scoped bundled-data bounds from the proven
   ownership protocol and board clock/reset assumptions. Review source and
   descriptor bundles too; do not equate zero critical CDC findings with closure.
3. Full receiver integration/timing, actual native calibration, sustained
   Ethernet/IIO and rollback qualification still precede `.18` canary and `.17`
   PPU Ethernet-only deployment. Preserve native 60 MS/s fine search, independent
   2.5 MS/s CI16 inspection, 120 ms valid dwells, 300 s scans and blind host GLRT.

No radio, PPU/main or primary production HDL changes. No deployment ETA follows
from this subsystem result. Goal remains active.

## Pins

RAM evidence: `/dev/shm/starlink-reset-cdc.nCo3Wwmo`.
Prepared SHA256: `28b4f9dbf7e61175b9dba8b87136438f6a134b88f111f0afb23e03ea344c736a`.
Synth DCP: `d2aad521da64bc29df429e965f05602e7a32af4683b93b13e889e4512147381c`.
Routed DCP: `6ac76c672827b6b227db586d316bf81921241cb6d15debd540f132c9ee6ee741`.
CSV: `14188bdee37e0e76d64c128ec7baf7efe33a70172e376fcb4ff735d0a1f50317`.
Parent numerical/archive dependencies remain pinned in source and the previous
output metadata/CDC reports. Set TMPDIR to a task-local RAM directory for Icarus;
the evidence tools require the documented pinned parent paths for re-auditing.

The first archive included 396 MB of copied/mutated regression CSVs and 40 MB
of duplicate regression checkpoints. That verified 191748423-byte archive is
retained under `oversize-package-v1` in the RAM evidence directory, SHA256
`93a81648ead2731ffdc3be5b2eb779b8cc9815830b98f81de4651e69a5bf4998`.
The Git-sized package excludes those regression-only CSV/DCP copies, retaining
test scripts/reports and the actual campaign CSVs and synthesis/routed DCPs.
No raw test files or unique implementation evidence were deleted.
