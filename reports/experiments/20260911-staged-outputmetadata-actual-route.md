# Parallel output metadata checks: actual FFT proof and measured route

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-split-output-metadata`.
FW `b1871495e`, HDL `7a2a271ea`. DO NOT MERGE or deploy this candidate.
Parent FW `1d0cd4b03c44f2dd0c67a2740d8efbfe18c34f0a`, HDL
`c0200466c06dae37907c467926935bc3ae379fa6`.

## Change

Compare live and replay output metadata against the actual first-word descriptor
in parallel, then select the one-bit comparison using the existing phase. The
original selected metadata mux remains for first capture and reader delivery.
No RTL state, delayed fault, added latency or assumed-constant descriptor.
An explicit unknown-selector fallback preserves original four-state behavior;
equality does not generally distribute over a four-state ternary mux.

The output-specific mailbox preserves the original framing, private writes,
publication, reader ownership and reset logic exactly. Other mailboxes are
unchanged; 22 runtime modules are compiled. This is a combinational alternative
to adding a registered descriptor certificate, whose extra lifetime/latency
would first need separate proof.

## Verification

- **652 distinct tests pass**: 637 regressions plus 15 new source/evidence tests.
  Focused preflights and seven archive tests overlap those totals.
- Component comparison: **9098 checks / 444 corrupted metadata cases**, covering
  each of 37 bits in either source, nonfinal/final, known inversion/X/Z;
  nonselected corruption, unknown selection, held final, publication/read/ACK
  and reset/fresh recovery. Four unsafe comparator mutants fail.
- Main actual FFT V3: **196.44 s**, all **64512 indexed values and full CSV match**.
  Service remains **3662/3662/4929/11729/3662/3662 clocks**, with the intentional
  reader stall excluded from the unchanged 5215-clock gate. Output identity
  checks: 39485 acceptances, 36352 live / 3133 replay, including held-final checks.
- Auxiliary V3: **128.21 s**, six new live/replay corruption/reset cases plus all
  inherited cases pass. Every new case blocks publication and recovers with
  512 fresh reads and one real reader release. Identity witness: 23597
  acceptances, 23554 live / 43 replay. All original deadlines remain.
- Synthesis **99.69 s**, route **48.97 s**. Both actual proofs and synthesis use
  the same source snapshot. Fresh evidence audits are required before routing.

## Preserved diagnostic corrections

The first component harness forced authorization high despite an unknown framing
result; the original mailbox can publish under that invalid caller premise.
The corrected harness includes the caller's current-framing authorization fence
for both implementations. No runtime change or stronger standalone X-safety
claim is made.

Actual V1 main passed, but its new auxiliary injection did not reach the split
concatenated input port. V2 diagnostics showed selected=held=`0000000003`, so
the run correctly failed and was never routed. V3 forces source tag/exponent
signals and proves selected metadata changed before checking the fault. All
four corruptions show framing=1 and replay_accept=0, then quarantine/recovery;
both replay resets also pass. All 22 runtime modules are byte-identical across
V1/V2/V3; only the testbench changed. Failed and corrected evidence is retained.

## Routed result — still failing

| Measurement | Split-capacity parent | Parallel output comparison |
|---|---:|---:|
| Worst overall setup slack | -1.938 ns | **-1.258 ns** |
| Worst 175 MHz same-domain slack | -1.938 ns | **-1.215 ns** |
| Total negative slack | -541.200 ns | **-328.306 ns** |
| Failing endpoints | 981 | 692 |
| LUT / FF | 2777 / 5788 | 2747 / 5793 |

All 8422 nets route without errors. Hold +0.062 ns, pulse +1.830 ns pass.
21 DSPs, 15 RAMB18s, no RAMB36s. Despite no new RTL state, implementation produces
five more registers. 114 inputs and 124 outputs remain unconstrained in this
OOC diagnostic. Clocks, route recipe and timing exceptions are unchanged.

The overall worst path is now **175-to-100 MHz bundled metadata**:
`output_bank/metadata_in_hold_reg[17]/C` to
`output_bank/metadata_out_hold_reg[17]/D`, zero logic, 1.146 ns data delay.
Do not ignore or false-path it without proving the ownership/stability contract.

The worst same-domain path starts at `output_bank/metadata_in_hold_reg[5]/C`,
crosses the live equality tree and current framing fault, and reaches
`owners[1].result_guard/active_private_reg/D`. Eight levels, 6.876 ns data delay,
5.366 ns routing (78%). Inverse commit follows through the same network.
The phase-before-wide-comparison path shortened, but setup is not closed.

## Next steps and deployment

Handle the remaining logic path and CDC contract separately. Investigate an
exact private output-validation boundary without delaying public fault vetoes,
and prove any extra latency against FFT return buffering/final write/replay.
For CDC, prove first-write/publication stability, synchronized request-to-reader
capture, real ACK-to-rewrite ordering and both reset epochs before deriving
scoped constraints under real board clocks. Neither change is implemented here.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain untouched.
No radios, PPU/main or primary production HDL changes. Full receiver timing,
CDC/reset/board clocks, actual 60 MS/s calibration and sustained Ethernet/IIO
remain gates before reversible `.18` canary, then `.17` PPU Ethernet-only
deployment with pinned rollback. Final verification still requires 300-second
scans, 120 ms valid dwells and blind host GLRT. No continuous RX or RF claim.

## Durable evidence

[Archive](20260911-staged-outputmetadata-evidence.tgz) and
[read-back receipt](20260911-staged-outputmetadata-evidence.json):
22641000 bytes, 10486 members, all bytes verified.
SHA256 `7b3909f3b4737d226741d9a5675eec6c6114ec81ec464d31c6dd91d993a8c6f4`.
Includes V1/V2 diagnostics, V3 sources/numerical/fault evidence, synthesis/routed
checkpoints, independent route audit, test results and implementation notes.
Historical fixtures are an explicit pinned parent-archive dependency.

V3 inventory `dc97c80ce1999e9a18053524c3dcd325d029705560c2425aef2e0fe05f20d1b7`.
CSV `210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Synthesis `bfdfd17a2bbea030937148187b73a621e6bf65c044468f0c7876cde295c257a1`.
Route `ee65ba286ece8625b60af30490ee33960f28e3eb93be60ac78e759968d8afcb1`.
RAM work area `/dev/shm/starlink-output-metadata.MB5fY8`; durable handoff is the
archive above, not RAM alone.
