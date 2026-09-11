# Held-final capacity isolation: actual FFT and measured route

Candidate branch (FW and HDL):
`codex/starlink-rx-only-do-not-merge-product-final-capacity`.
FW `d49944669`, HDL `44cf696a9`. DO NOT MERGE or deploy this candidate.
Parent: FW `967db3daa1f69e9ac17960c33d1533c7afb0cb03`, HDL
`0705316ad41b7f056d6acaae82e28a4c9a4e8a13`.

The product stage now refuses same-edge refill of a held LAST. Its existing
publication-qualified retirement and fault/reset vetoes remain unchanged.
Nonfinal streaming and first-reference write-through remain continuous. Only
one runtime assignment changes; the other 20 modules and complete top wiring
remain exact. Actual-FFT monitors check that a healthy producer stays quiet
during LAST and that subsequent forward jobs wait for actual bank ownership.

## Results

- 606 regressions plus 10 new evidence tests pass: **616 distinct tests**.
  Focused 26-test preflight and seven archive tests overlap those totals.
- Actual FFT main passes in 212.37 s: **64512 numerical records match**, including
  identical CSV SHA256 and unchanged 3662/3662/4929/11729/3662/3662 service clocks.
  The intentional reader stall remains excluded from the unchanged 5215 gate.
- Actual auxiliary passes in 108.49 s: original six ACK cases, 12 forward
  receipt cases and 12 product fault/reset cases, all with fresh recovery.
  Final-capacity checks: main 98 final cycles / 107 starts; auxiliary 166 / 54.
- Synthesis 104.87 s; route 43.25 s. Both actual proofs and synthesis share the
  pinned prepared source inventory. No constraints or deadlines were relaxed.

| Routed measurement | Integrated parent | Capacity isolation |
|---|---:|---:|
| Worst setup slack | -4.115 ns | **-3.252 ns** |
| Total negative slack | -3456.457 ns | -2279.503 ns |
| Failing endpoints | 2297 | 1330 |
| LUT / FF | 2810 / 5781 | 2804 / 5780 |

All 8469 nets route without errors; hold +0.070 ns and pulse +1.830 ns pass.
21 DSP, 15 RAMB18, no RAMB36. **Timing still fails** and remains worse than the
pre-product-stage forward-receipt reference (-1.567 ns / -497.191 ns / 681).
There are also 114 unconstrained inputs and 124 outputs in this OOC diagnostic.

Worst path: `cutover/fault_reasons_reg[7]/C` to
`admission_gate/snapshot_good_reg[6]/R`, through quarantine/current-fault
qualification, final readiness, kernel READY and admission snapshot reset.
12 levels, 8.358 ns data delay, 6.352 ns routing (76%). Another path reaches
arithmetic clock enable through the same network. The local capacity edit
helps but does not create a complete physical control boundary.

## Next step and deployment gates

Investigate block-scoped producer capacity derived from an actual destination
reservation, separating local nonfinal streaming capacity from final-publication
authorization. Prove real ownership, epoch expiry, unexpected capacity loss,
current faults and reset edges first. Do not just delay a shared fault or trust
stale READY. Repeat actual numerical/service and fault campaigns before route;
retain the better forward-receipt physical reference. This next architecture
is not implemented here. More TX removal does not address the measured path.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
untouched. No radio, PPU/main or primary production HDL changes. Full receiver
timing/CDC/reset/board clocks, actual 60 MS/s RX calibration and sustained
Ethernet/IIO remain before reversible `.18` canary, then `.17` PPU Ethernet-only
deployment with pinned rollback. Final checks remain 300-second scans, 120 ms
valid dwells and blind host GLRT. No continuous RX or RF accuracy claim here.

## Preserved evidence

[Verified evidence archive](20260911-staged-finalcapacity-evidence.tgz) and
[read-back receipt](20260911-staged-finalcapacity-evidence.json):
13804120 bytes, 5332 members, all member bytes verified.
SHA256 `2d6cbccd814457936228571176ccbac0619af9324c032ab542e42a4f2b4ce847`.
Includes prepared RTL/Tcl, both numerical/corner-case logs, synthesis/routed
checkpoints, independent route audit, test sources/results and implementation
notes. Historical fixtures are an explicit parent-archive dependency, not
silently assumed part of this packet.

Prepared inventory `408204bad0b135494839b37ce242f2cc720e9e918e293aaedcdc0d6a0105a0f6`.
CSV `210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Synthesis `bc085a9db18734818483d396c59b1d979767556049c62fffa37914e4c8abc94d`.
Routed checkpoint `43a0aba1274f5af69ec5e2adf86c0beb4bf181430009ffa37a32d9fe8cd8cb5a`.
RAM workspace: `/dev/shm/starlink-final-capacity.vMIiHM`; durable archive above
is the handoff source, not RAM alone.
