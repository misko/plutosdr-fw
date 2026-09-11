# Balanced handoff: targeted path fixed, subsystem setup still fails

DO NOT MERGE or deploy this candidate.
FW/HDL branch: `codex/starlink-rx-only-do-not-merge-balanced-handoff`.
FW `a2313deeb`, HDL `d999ec011`.

Replace only the current 70-bit product handoff equality with a balanced tree
of small comparisons. No register, pipeline latency, delayed fault veto or
clock change. The reset-safe source/output mailbox structure is unchanged.

## Verified result

- 682 regression tests pass, including five new component/source tests.
  Component comparison checks all 70 bits and four-state cases in 2841 checks;
  three deliberately incomplete comparators are rejected.
- The first real-FFT main run exposed a monitor scheduling race at a deliberate
  same-edge metadata force. V2 moves only the monitor observation 1 ps later.
  Recorded before/reference/settled values demonstrate the delta-cycle race.
  All 22 runtime modules remain byte-identical across V1/V2; V1 is not routed.
  28 focused tests pass after this correction; this is not another full-suite run.
- Eight new actual-evidence tests pass (690 distinct regression/new-evidence
  tests), plus seven overlapping archive tests. Both corrected actual FFT
  campaigns pass: **198.61 s main / 129.69 s auxiliary**.
- All **64512 indexed numerical records and the complete CSV match the parent**.
  Service remains **3662/3662/4929/11729/3662/3662 clocks**. Actual identity
  witness: 500573 main checks (22155 forward-owned), 303647 auxiliary (705 owned).
- Synthesis takes 98.55 s; unchanged-constraint routing takes 49.32 s.

## Physical comparison

The exact prior exponent-to-output-publication endpoint pair improves from
**−1.370 ns to +0.086 ns**, with 12→8 logic levels and six→zero CARRY4 stages.
Data delay falls from 6.919 ns to 5.576 ns. A separate pinned routed inspection
measures the original endpoints directly; this is not inferred from a changed
worst-path summary.

However, **overall timing regresses to −1.736 ns WNS**, versus −1.496 ns.
TNS is −430.075 ns (previously −436.221), with 715 failing endpoints (675).
New worst path: `output_descriptor_payload_reg[4]/C` through replay metadata
comparison/current framing fault to `output_control/phase_reg[0]/D`.
Ten logic levels, 7.447 ns data delay, including 5.751 ns routing (77.2%).

All 8419 nets route without errors; hold/pulse pass. 2727 LUTs, 5789 registers,
21 DSPs, 15 RAMB18s. Read-only CDC inspection confirms the prior reset cleanup:
exclusive first-to-second-stage fanout, registered purge source, nine CDC-3
informational synchronizers and 208 CDC-15 bundled-data warnings; no CDC-1 or
CDC-10 critical findings. No constraints changed. OOC still has 114 inputs and
124 outputs unconstrained; this is not full receiver or board signoff.

## Next step and deployment

Retain both branches; do not promote this candidate solely for the local path
improvement. Next investigate the output-validation/state feedback path, keeping
the original current fault veto and real publication/reader ownership. Any
registered validation must bind to the actual descriptor and avoid stale
authorization or circular phase/READY dependencies. Re-run actual FFT and route
after the next change. Bundled-data timing qualification remains a separate gate.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
unchanged. No radios, PPU/main or primary production HDL changes. Full receiver
timing/CDC, board clocks, native RX calibration and sustained Ethernet/IIO remain
before reversible `.18` canary and `.17` PPU Ethernet-only deployment, pinned
rollback, 120 ms valid dwells, 300 s scans and blind host GLRT.

## Evidence

[Archive](20260911-balanced-handoff-evidence.tgz),
[readback receipt](20260911-balanced-handoff-evidence.json): 43439808 bytes,
5524 verified members, SHA256
`1096bed5e30bb0e5facefd2d997c6cb86fff34b0dbb43523daa56b20336ca076`.
Includes failed/corrected evidence, actual CSVs, checkpoints, tests and detailed
implementation notes. Duplicate regression CSV/DCP copies are excluded;
identical generated vendor VHDL is retained once with equality checked.
Raw local artifacts are preserved.

Prepared V2 SHA: `c6b632215fbd08fa2c06150652f39a3967163566eeaac8c01138c7475c1c429e`.
Routed DCP SHA: `8603dff0a926c91cf67f23360e7dbe8bc79ea712eecd680132be6ddd693614e9`.
Parent: [reset-receipt actual route](20260911-reset-receipts-actual-route.md).
