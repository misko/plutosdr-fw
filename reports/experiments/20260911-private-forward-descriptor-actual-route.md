# Private forward descriptor: targeted closure, subsystem still fails

The private descriptor now loads from local reservation capacity in a separate
register block. Current fault/state/publication handling is unchanged. A copy
loaded on a rejected reservation is permitted to differ only behind identical
quarantine, with reservation, capture and valid replay disabled until reset.
All 36 parent runtime modules remain unchanged; two derived modules are added.

1,753 tests pass, including four-state controls, descriptor X/Z, unsafe mutants,
exact transforms and route-admission checks. Both actual generated FFT campaigns
retain all 64,512 numerical words and 4,178 service clocks (23.874 us at 175 MHz).
All 65 fault/reset/delay cases pass. The auxiliary independent reference observes
six rejected descriptor loads and 910 quarantined differences across 1,376,591
comparisons; other bank state, current controls and valid payload remain exact.

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no exceptions:

- WNS -1.304 ns, TNS -663.577 ns, 1,647 / 14,493 failing endpoints.
- Parent WNS -1.426 ns, TNS -446.926 ns, 839 / 14,510 failing endpoints.
- All 70 descriptor CE pins measured; worst +0.129 ns (previously -1.348 ns).
- All 70 descriptor data pins measured; worst +2.226 ns.
- Prior product occupancy +0.892 ns and identity +0.316 ns remain passing.
- 2,741 LUT / 5,907 FF / 16 RAMB18 / 21 DSP; 8,562 nets routed.
- Hold +0.052 ns, pulse +1.830 ns; no combinational or latch loops.
- Nine CDC-3 / 208 CDC-15, no CDC-10; 114 inputs / 124 outputs unqualified.

Worst path now reaches output-stage occupancy from expected product metadata
through current preflight/publication checks (eight LUT levels, 6.963 ns data
delay). Output-bank request toggle is next at -1.138 ns. Aggregate slack and
failure count regress: no overall closure, promotion or deployment is claimed.

Next apply registered ownership receipt to private output-slot retirement,
keeping current output replay acceptance and bank publication unchanged. Verify
retained-controller receipts, slow-reader stalls, descriptor/tag identity,
pending resets, late faults and no duplicate publication or post-publication
writes before routing again. Current publication timing remains a separate gate.

## Retained evidence

Branch `codex/starlink-rx-only-do-not-merge-private-forward-descriptor`:

- FW `dac9d92d6e10af84c73fdf5ab694a192bec77dd5`.
- HDL `e61c020194d015af8247e6b6a3c7eceee1a995f9`.
- Main inventory `ec24a2e7946f68f5d906cbc4435f4613b436e2550d998d57955a15ae9b2a3e6e`.
- Auxiliary inventory `72063709cdfd36cc0de3d61eebfd99a6ae65b4323de0f0959363dbcc6c5e35ca`.
- Routed DCP `6e54cf83bae142e87493efc4cc67a341ecc3d351a276dbfeb252c11a86efed4e`.
- [Verified archive](20260911-private-forward-descriptor-evidence.tgz):
  16,943,887 bytes / 31,712 members, all members read back and verified.
- SHA256 `62506b40b831074146ba30955d76d3e64bac9e075e2cc2f3e942e2677c5e93e6`.
- [Archive receipt](20260911-private-forward-descriptor-evidence.json).

Primary HDL stays `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s
fine search and independent 2.5 MS/s inspection remain required and unchanged.
Full receiver timing/CDC/reset, actual calibration, continuous RX and real
IIO/Ethernet must pass before reversible PPU deployment to .18, then Ethernet-only
.17. No radios or PPU/main were touched; .14/.20/.21 remain excluded.
