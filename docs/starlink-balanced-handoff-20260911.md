# Balanced current handoff identity — DO NOT MERGE

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-balanced-handoff`.
Parent FW `fd2174c3a9b97229ec6e3c9c378255a15a156ca5`, HDL
`cf14f5d2d7dd2bbf8cc64c96a64356aadf2734bf`.

## Implementation and preserved scope

The parent route's same-domain critical path crosses a 70-bit product handoff
equality implemented with six CARRY4 levels, then current fault/publication
logic. Replace only this equality with 24 parallel comparisons (23 three-bit
leaves and one one-bit leaf), four six-leaf groups, then the final reduction.
Keep attributes preserve the small comparison boundaries. The expected
descriptor still uses the original current phase/start/exponent sources.

No register, sampled certificate, pipeline stage, clock change or delayed veto
is added. All 70 bits and logical-equality four-state behavior are preserved.
The original equality's truth table is false for any known mismatch, unknown
if only uncertain bits prevent a decision, and true otherwise; the grouped
reduction has the same behavior. Original handoff fault, ACK, completion and
publication consumers are unchanged. The reset-receipt cleanup is retained.

Exactly one compiled runtime source changes. All 22 runtime modules are pinned,
and an exact inverse test proves the entire top and all other runtime sources
match the reset-safe parent after undoing the equality block. An additive
actual-FFT monitor compares the candidate with the original current expression.

## Verification and retained diagnostic

- **682 regression tests pass in 86.33 s**, including five new component/source
  tests. Component comparison performs 2841 checks across all 70 bits, either
  source, known inversions/X/Z, known mismatch with another unknown, and random
  vectors. Three unsafe variants omit top/middle/exponent bits and are rejected.
- Actual V1 main stopped at completion corruption boundary 6: the existing
  driver forces product metadata on the same negative edge as the new monitor.
  The monitor observed the newly forced reference before the balanced
  combinational network's delta cycles settled. V1 main is rejected, not routed.
  V1 auxiliary and synthesis completed; all diagnostic files are retained.
- V2 changes **only the monitor** to observe 1 ps after that negative edge,
  well before the next positive sampling edge. It records before/reference/
  settled values. The corrected log shows `before=1 reference=0 settled=0`
  on the force, and `before=0 reference=1 settled=1` on release. Existing
  completion fault rejection/recovery then passes. All 22 runtime sources
  are byte-identical between V1 and V2.
- **28 focused tests pass in 1.67 s after this monitor correction**. This is
  not a second execution of the complete 682-test suite. The corrected actual
  main/auxiliary campaigns independently exercise the same runtime.
- **Eight new actual-evidence tests pass**, plus seven overlapping archive
  tests, in 1.32 s. They reject missing/duplicate/short/incorrect identity
  evidence and prevent routing without the compiled main witness. They also
  verify the source-identical monitor correction and retained rejected V1.
  Distinct regression/new-evidence total: **690**.

V2 main actual FFT completes in **198.61 s**, all **64512 indexed numerical
records and the complete CSV remain byte-identical to the parent**. Service is
unchanged at **3662/3662/4929/11729/3662/3662 clocks**. The intentional reader-
stall context is not used for the unchanged 5215-clock coarse service bound.
New current-identity witness: **500573 checks, 22155 forward-owned checks**.

V2 auxiliary completes in **129.69 s**, retaining all output corruption/reset,
ACK, forward-receipt and product-stage boundary tests. New identity witness:
**303647 checks, 705 forward-owned checks**. V2 synthesis takes **98.55 s**.
Both actual campaigns are re-audited against the same frozen sources before
routing; no stopped/failed job is substituted for a successful proof.

## Measured routing — targeted path passes, subsystem still fails

Route completes in **49.32 s** with the unchanged 100/175 MHz OOC recipe.
A separate read-only query of the exact original endpoint pair demonstrates:

| Original exponent-to-publication path | Parent | Balanced handoff |
|---|---:|---:|
| Setup slack | −1.370 ns | **+0.086 ns** |
| Logic levels | 12 | 8 |
| Data delay | 6.919 ns | 5.576 ns |
| CARRY4 stages | 6 | 0 |

This is a local physical improvement, not closure of the complete subsystem.
Overall **WNS is −1.736 ns**, versus the parent's −1.496 ns; TNS is
−430.075 ns versus −436.221 ns, with 715 failing endpoints versus 675.
The same-domain worst is also −1.736 ns. No timing exceptions changed.

The new worst path starts at `output_descriptor_payload_reg[4]/C`, crosses
output-bank replay metadata equality/current framing fault and common control,
and ends at `output_control/phase_reg[0]/D`. It has ten logic levels and
7.447 ns data delay, including 5.751 ns routing (77.2%). The next change should
target this output-validation/state feedback path, retaining current fault
vetoes and actual ownership. A delayed check must not authorize publication
against stale metadata or create a dependency cycle with phase/READY.

All 8419 nets route without errors. Hold +0.058 ns and pulse +1.830 ns pass.
2727 LUTs, 5789 registers, 21 DSPs and 15 RAMB18s. 114 inputs and 124 outputs
remain unconstrained in OOC. The reset structural inspection still confirms
exclusive first-to-second-stage fanout and a registered purge source: nine
CDC-3 informational synchronizers and 208 CDC-15 bundled-data warnings,
with no CDC-1/CDC-10 critical findings. This is not board-level CDC signoff.

Retain both candidates for comparison; do not promote this route simply because
the targeted path and LUT count improved. A broader control-path/physical result
must improve before integration. Source/descriptor/output bundled-data timing
qualification remains separate from this same-domain logic work.

## Pins and preservation

RAM evidence: `/dev/shm/starlink-balanced-handoff.5K7fHIYq`.
V1 prepared SHA: `ccd6dc48b97cc486332d74ff785554c6bacbb7b34c84af584ca4c561c3b4add1`.
V2 prepared SHA: `c6b632215fbd08fa2c06150652f39a3967163566eeaac8c01138c7475c1c429e`.
CSV SHA: `14188bdee37e0e76d64c128ec7baf7efe33a70172e376fcb4ff735d0a1f50317`.
Synth DCP SHA: `d04ab6379d6f0694ad0e1a89f1292d01d9220a17d7f6d322dd9251aefd7787fa`.
Routed DCP SHA: `8603dff0a926c91cf67f23360e7dbe8bc79ea712eecd680132be6ddd693614e9`.

The archive retains both source snapshots, failed/successful actual logs,
actual numerical CSVs, synthesis/routed checkpoints, tests and inspections.
Inherited regression-only CSV/DCP copies are excluded. Byte-identical generated
vendor VHDL is included once from V2 synthesis, with duplicate equality checked
before omission. These exclusions do not remove any raw local artifact.

No radio, PPU/main or primary production HDL changes. Native 60 MS/s fine
search and independent 2.5 MS/s CI16 IIO inspection remain required. Full
receiver timing/CDC, board clocks, actual native RX calibration and sustained
Ethernet/IIO still precede reversible `.18` canary then `.17` PPU Ethernet-only
deployment with pinned rollback, 120 ms valid dwells, 300 s scans and blind
host GLRT. OOC success alone cannot satisfy those gates. Goal remains active.
