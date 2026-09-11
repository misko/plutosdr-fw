# Post-route physical experiment — DO NOT MERGE, no deployment

The latest private-input candidate regressed. Return to the retained
private-certification and guard-fact references. Their worst paths are about
80% routing delay. The pinned diagnostic recipe previously ran opt/place/
physical-opt/route but no post-route physical pass. Test one bounded
`phys_opt_design -directive AggressiveExplore` pass on each existing routed
checkpoint. No new placement, RTL, clock changes, exceptions, or radio actions.

Vivado 2022.2 supports post-route physical optimization:
[UG904](https://docs.amd.com/r/2022.2-English/ug904-vivado-implementation/phys_opt_design).
This is a physical-flow experiment, not a substitute for simpler registered
control, post-implementation functional proof, or full receiver signoff.

## Frozen inputs and gates

Branch `codex/starlink-rx-only-do-not-merge-postroute-physical`, based on FW
`eda2c6dce8d86e794427ee3d153a75d8617ad9d3`. The FW HDL gitlink remains
`cf4b702305b78d8992705aa4bf10cf4bc7ed5977`; no HDL checkout or edit was needed.

The runner re-audits the original terminal results and pinned source/DCP
receipts, verifies original audit equality, and generates the new Tcl from the
SHA-pinned original recipe by replacing exactly its four implementation steps
with the one physical pass. All path checks, 100/175 MHz clock checks, checkpoint
receipts, complete cross-clock reports, CDC and unconstrained reports remain.
New outputs only; 660-second subprocess limit, two Vivado threads per run.

The report auditor now has read-only mode and a separate report-only parser.
The parser explicitly cannot certify source/checkpoint provenance. Default
auditing retains the original recipe SHA and no-overwrite behavior. **19 tests
pass**: original auditor corruption controls, exact recipe inverse, changed
recipe rejection, read-only parent checks, report-only provenance separation
and constraint command preservation.

After each physical pass: original and generated recipes, input DCPs and
orchestration sources unchanged; parent re-audit unchanged; inherited XDC
commands byte-equivalent after stripping only comments/blank lines. New DCP
SHA matches Tcl receipt. All-clock-pair reports agree with global timing
summary; all routable nets fully routed, no routing errors. No old result is
overwritten and no clock crossing is waived.

## Measured results

| Reference | Global WNS before/after (ns) | TNS before/after (ns) | Failing endpoints before/after | 175 MHz same-domain WNS after (ns) |
|---|---:|---:|---:|---:|
| Private certification | -1.452 / -1.364 | -451.168 / -448.933 | 704 / 704 | -1.364 |
| Guard facts | -1.340 / -1.307 | -463.636 / -457.279 | 821 / 822 | -1.167 |

Both commands and source/report audits pass on the first attempt (22.54 and
23.85 seconds). **Both physical timing gates still fail.** Guard facts gains
one failing endpoint despite improved worst/total slack. This is not an overall
functional or deployment promotion. Vivado also warns that the negative slack
is too large for post-route optimization to be likely to fix it completely.

Private certification: 2746 LUT / 5668 FF / 21 DSP / 15 RAMB18, 8352 routed
nets, hold +0.070 ns, pulse +1.830 ns. Worst path is held scheduler phase into
inverse guard fault diagnostics, eight logic levels, 6.933 ns data delay.

Guard facts: 2812 LUT / 5691 FF / 21 DSP / 15 RAMB18, 8469 routed nets,
hold +0.051 ns, pulse +1.830 ns. Overall worst is now the held metadata crossing
from output-bank fast writer to slow reader (-1.307 ns); the same-domain fast
path is -1.167 ns. Keep the crossing visible until CDC protocol, stability and
physical constraints are independently qualified. Same-domain improvement is
not global timing closure. Both builds retain 114/124 unconstrained I/O.

RTL/numerical tests are inherited, not newly rerun: private certification had
449 passing tests; guard facts had 464. Both had 64512 exact actual FFT records
and unchanged service intervals. No claim of a new post-implementation
functional simulation or formal equivalence follows from this physical pass.

## Next implementation boundary

The evidence does not justify more TX removal or a blind directive sweep.
Keep post-route optimization as a measured finishing step, and shorten the
shared current-control paths. The retained input checker selects a 70-bit bank
metadata bus by phase before equality, then carries the result through delivery
and result faults. Investigate comparing each held bank locally before selecting
a one-bit result, including position/last checks where applicable. This would
preserve current-edge checks without inserting a delayed fault veto. It is a
hypothesis, not a implemented change or a promised timing benefit.

For a two-bank comparison refactor, first prove four-state behavior: moving a
ternary selector through equality is not automatically equivalent for X/Z
selectors. Preserve original fallback or constrain/prove known phase before
admission. Test both owners, every identity bit, wrong framing, unknowns,
duplicate start, core stalls and reset around admission/publication. Compare
the real checker against the original, then actual FFT and unchanged route.
Do not weaken diagnostics or remove current publication/reset vetoes.

The reset/publication boundary remains relevant, but changing reset semantics
is not justified simply because one physical path originates at reset release.
Held-bundle crossings also need explicit protocol/CDC qualification; changing
clock constraints is a separate reviewed step, not a way to hide violations.

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s RX calibration and Ethernet/IIO verification precede
`.18` reversible canary, then `.17` PPU Ethernet-only deployment with rollback.
Final gate remains a 300-second scan, 120 ms valid dwells and blind host GLRT.
No radio, PPU, main or primary production HDL change.

## Artifact pins

Generated Tcl: `1595ce0202e985e9937bfb98801008ec0cb6fe6b2aaed12cd880fa91cdfed5b6`.
Certification parent DCP:
`5e388b0bd65cab4b5f703ecb019c5f53c1959595f22c7613febbe57f46a77ec6`;
new DCP `1d3129f9ca10a89ab11e84b595ad591b69a01ce65a78240537d5be0552668cef`.
Guard-facts parent DCP:
`ab681d26848908f8a5454479611d14a74040ee00fafeff525f6b074ee71f287e`;
new DCP `569a91801822ff351762cba9783d032d1b0611a395a375fd1383c161d5fbadba`.
Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/postroute-physical-worktree-v1`.
Sibling artifacts: `staged-{certification,guardfacts}-postroute-v1` and
`staged-postroute-tests-v1.xml`.
