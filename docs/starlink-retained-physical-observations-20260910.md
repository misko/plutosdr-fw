# Retained-output synthesis and diagnostic route: timing FAIL

This is the exact isolated retained-output runtime qualified by parent actual
13931 (seven contexts, 38 complete transforms, two aborted forwards). No runtime,
FFT arithmetic, vector, clock, exception or guard was changed for these runs.
It is not a physical release, board-clock qualification, continuous source-rate
test, receiver integration or radio result. The parent owned both vendor runs.

| Observation | Synthesis 8892 | Diagnostic route 5802 |
|---|---:|---:|
| Original process exit / elapsed | 0 / 207.8867 s | 0 / 74.2778 s |
| LUT / FF | 2239 / 4758 | 2334 / 4768 |
| DSP48E1 / RAMB18 | 21 / 15 | 21 / 15 |
| Black boxes | 0 | 0 |
| Routed nets / routing errors | not run | 7224 / 0 |
| Setup WNS / TNS | not qualified | **-4.068 / -1952.796 ns** |
| Setup failing endpoints | not qualified | **1266** |
| Hold worst slack / failing endpoints | not qualified | +0.052 ns / 0 |

Exit zero means the commands/reports completed; it does not mean timing PASS.
The mapped hierarchy retains one FFT, three payload banks, two result guards
and one product unit. Synthesis adds 294 LUT and 211 FF versus the accepted L1
synthesis comparator, with unchanged DSP/RAM counts. The earlier 223-bit source
register inventory is a declared-bit count, not a mapped FF estimate.

## Frozen authority and observations

- Qualified v5 manifest: `c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8`.
- Prepared synthesis v2 inventory: `4a0bbd1b07ea94c51e5b001dbbd7c48b601d1abd8659253a318e3d3f6d357ecb`.
- Synthesis runner: `79aca85d52146627a2584fa2d3443ead35492ecfc279f156717794535f67f660`.
- Synthesized DCP: `d0a5e0c70d960ab6cf5c9b616610df88c2599ed73932f4fc9c8415c10f4ff840`.
- Route runner: `034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a`.
- Routed DCP: `f93d0280e5ace9756fe99e1b118b8e12b57dd1b4b45bd14820aa70a1ad209cc8`.

Exact 16 runtime files were marked SystemVerilog, with retained output and
R1/B1/O1/L1 enabled; no test/reference RTL was synthesized. Vivado 2022.2,
xc7z010clg400-1, two threads, frozen factory/kernel, original OOC directives,
literal comparable 100/175 MHz XDC and unchanged opt/place/phys-opt/route sequence
were used. All four clock pairs have 20 max and 20 min paths recorded. Checkpoints
were preserved before observational reports. Original/copy source checks and
generated-IP before/after receipts remained equal.

The top routed path is **same-domain** island_175:
`product_bank/metadata_out_hold[24]` through input-guard identity/fault and
cutover/common-fault logic to `owners[0].result_guard/descriptor[64]/CE`.
Data delay is 9.493 ns: 1.758 ns logic, 7.735 ns routing, ten LUT levels.
This failure cannot be dismissed as the independent-clock rounding warning.
Cross-clock setup paths also fail: 100→175 -1.255 ns and 175→100 -1.494 ns.
100→100 setup is +2.572 ns. No new false path or clock relaxation was applied.

CDC remains **unqualified**: five critical, 139 warning and three informational
findings. Four critical findings concern first-stage request/ACK synchronizer
fanout through reset-idle checks; another concerns decoded slow-purge completion
before synchronization. Functional reset sequencing does not constitute a CDC
waiver. Independent rounded primary clocks also trigger the common-period
warning; this is not a board-derived clock model. There are 114 inputs without
input delays and 124 outputs without output delays, intentionally preserving
the comparator's OOC constraints rather than claiming external-I/O signoff.

## Preparation checks, evidence and publication

Own synthesis preparation: 25 PASS in 1.15 s; independent parent: 25 PASS in
1.19 s. Own/parent route preparation: eight PASS in 0.08 s each. These are
offline admission/report-stub tests, not vendor timing evidence. Initial v1
preparation and its bounded containment correction are preserved; no runtime
or arithmetic test was rerun merely for collection.

Raw parent roots under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:
`retained-synthesis-parent.JqxbVb4y` and `retained-route-parent.I7WoLBxe`.
Complete raw run products remain in place. Compact archive includes both DCPs,
all final reports/warnings, owner execution/command receipts, full preparation
v1/v2, generated-IP wrapper and full raw inventories. Parent pytest case trees
(including deliberate symlink controls) are not vendor products; their test
log/XML receipts are included without duplicating those trees.

Archive `artifacts/retained-physical-observations-v1.tar.gz`:
SHA256 `39388ceeba0829e16b8a58fa83f7fc60f48b7baef9b6298115ee07a3a99cde83`,
6,448,360 bytes, 280 safe regular members / 279 hash-and-length receipts.
Full synthesis+owner inventory: 210 files / 33,742,341 bytes; route+owner:
39 files / 5,979,161 bytes; both preparation inventories: 94 files each.
All selected and full raw inventories were rehashed after collection unchanged.
The initial collector rejected pytest symlinks before creating output; its
failure receipt is preserved separately. Collector verification is a packaging
check, not part of the earlier 25/eight test counts.

Publication is confined to the existing do-not-merge alternative branch, HDL
first then FW. No primary gitlink, radio, receiver profile, physical constraints
or runtime edits are authorized by this evidence. Further cone analysis is
read-only; another implementation or vendor run requires separate review.
