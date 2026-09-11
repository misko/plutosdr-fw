# Balanced forward identity: exact behavior, mixed timing

**Timing still fails. No deployment or primary HDL promotion.**

The descriptor check is now 24 parallel comparison groups and four reduction
groups, with kept intermediate nets. A separately derived bank/top preserves
all 29 parent runtime modules, same-edge fault behavior, RAM/seal/replay/reset
and the recently fixed product-publication veto. No logical state or extra
fault latency is introduced.

## Functional and physical evidence

**1,412 distinct tests pass:** 1,381 regression plus 31 route-admission tests.
The separate 34 component tests are already included. Twenty-one bank scenarios
compare controls, valid replay data and private progress against the parent.
The comparator matches the old four-state expression on 20,351 directed/random
vectors, including every bit and X/Z; two broken reductions are rejected.
These checks are not an exhaustive formal state-space proof.

Both actual generated FFT campaigns match all **64,512 numerical words** and
retain **4,178 service clocks / 23.874 us at 175 MHz**, below the 5,215-clock
budget. All 43 fault/reset/delay cases pass. The new actual comparison observer
checks 88,545 main cycles / 9,216 captures and 501,624 auxiliary cycles / 50,167
captures. Numerical CSV and inherited observer results remain unchanged.

The independent routed-checkpoint inspection observes all **24 group nets and
four reduction nets**, with zero carry cells in all 28 upstream cones. The
targeted path is now LUT-based: synthesis did preserve the balanced structure.
The final unkept AND may fold into its consumer. Observation is source/checkpoint
pinned and adds no timing constraints or design changes.

## Routed comparison

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no new exceptions
or clock relaxation. The complete actual campaign precedes routing.

| Metric | Product-fence parent | Balanced identity |
|---|---:|---:|
| WNS / TNS | -1.224 / -519.788 ns | -1.420 / -420.378 ns |
| Setup failures | 1,217 / 14,494 | 939 / 14,505 |
| Same-domain 175 MHz WNS | -1.174 ns | -1.420 ns |
| LUT / FF | 2,780 / 5,907 | 2,805 / 5,912 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Failure count and aggregate negative slack improve, but worst-case timing
regresses. The previous candidate remains better on worst-case slack; neither
is timing-closed. Do not remove the publication fix to recover timing.

All 8,675 nets route without errors. Hold +0.013 ns and pulse +1.830 ns have
zero failures; combinational/latch-loop counts are zero. 114 inputs and 124
outputs remain OOC-unqualified. CDC reports nine CDC-3 and 209 CDC-15 warnings,
no CDC-10. The added warning is source metadata receiver bit 20's replica;
reset-release also uses a replicated CDC source. These require full physical
qualification. The scalar fault register remains the direct synchronizer source.

Worst path is forward-bank descriptor bit 36 into the forward guard's latched
fault reason: eight LUT levels, 6.989 ns data delay, **77.306% routing**. The
carry chain was removed, but the current-fault/readiness path still traverses
shared guard/control logic. Next investigate a registered private bank-status
boundary while retaining immediate local RAM/seal/replay rejection and public
publication vetoes. Prove bounded fault propagation and no publication, ACK,
reuse or reset leakage before another actual campaign and route.

## Branch and retained artifacts

Branch `codex/starlink-rx-only-do-not-merge-balanced-forward-identity`:

- FW `d3d6e86c789cc6bfa691af4ee79fed51390b68b1`.
- HDL `10996fd95c79899504785dd1aca4ca84d5bba3c2`.
- Main inventory `3fdb6238d577ede67da2c3d4778d3ddb1a9e07f19a311f72482051d95d2a15a1`.
- Auxiliary inventory `775bd7a3da5be744d7fa4bc93728003332923b7e80e320ae44a3f8a69c92fc03`.
- Routed DCP `cb0bf25b79c63c903377649130efba86e3bc676a93efe46a721f73aec75d1b60`.
- [Read-back verified archive](20260911-balanced-forward-identity-evidence.tgz):
  15,958,153 bytes / 12,199 members; SHA256
  `42dd974661278933359f28002d7e9c0d1627adc6ab7f2d8084c99c7189a76d86`.
- [Archive receipt](20260911-balanced-forward-identity-evidence.json).

Archive includes prepared sources, full actual streams/logs, both checkpoints,
raw route/netlist reports and tests. Historical regression payload duplicates
remain local with a hash inventory. Primary HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
Native 60 MS/s fine and independent 2.5 MS/s inspection remain required. Full
receiver timing/CDC/reset, calibration, continuous RX and IIO/Ethernet must pass
before pinned reversible PPU deployment: `.18` canary, then `.17` over Ethernet.
No radios or PPU/main were touched; `.14/.20/.21` remain excluded.
