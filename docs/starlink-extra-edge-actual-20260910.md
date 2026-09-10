# Phase-aligned baseline actual run passes the qualified scope

Original actual handle **22816 exited0**. Both complete original numerical
CSV traces match the historical baseline exactly, both added extra tasks
complete, and the unchanged runner plus independent qualified-observer
receipt audit pass. This is **R0/D0/S0 only, not an original raw217 pass**.
No experimental mode, physical run, radio test or promotion was performed.

Measured FW `c9e191f898a146ff08ab5b6c9c848d747fc552d7` /
HDL `bed131df5740315da90d1742a0ff956d61990b06`, tested source
FW48b88f678 /HDL12ce2854. All seven runtime modules remain ae50 unchanged.
The only prepared stimulus change is the previously reviewed phase-aware
alignment and held-final checks in the added kind0/1 fault tasks; original
stimulus, old1ps checkers, reset kinds2/3, arithmetic and gates stay literal.

Run directory `/tmp/starlink-completed-input.5EaJuD/extra-edge-prepared-v1`;
R0/D0/S0/extras1/FAST175/QUICK0. Vivado2022.2/two threads, explicit SuSE
library path, one launch/no restart. Before/after freeze verification passes:
`8efa2657fd43d4c7d2804d90abf9aa169fb8d916136ee681d38d4b533885ad92`.
Start08:16:56UTC, exit08:22:56UTC, wall359.77s, user368.86/system2.07s,
peak RSS836928KB. All27 warnings are unchanged from8757 after normalizing
only the output-directory path; none is waived.

## Completed evidence

Both original CSVs:325750lines, byte equal and historical SHA256
`b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d`.
Both extra CSVs:33131lines, byte equal, SHA256
`d3a4aaff96db5c9a9d15cc9f4af8400f42b52fd4f97c08712dfce4d3d585562b`.
The extra hash is an observed new trace, not a retuned golden.

Both independent extra receipts assert exactly two final faults, three held
final stalls, two one-sided resets and four healthy recoveries. The final
shadow receipt has717760checks,504864activechecks,36identityconsumptions,
zero private differences, two final-fault edges,78830owned-stall edges
and40reset-owned edges. Simulator finishes at2050740106537fs.

The independent frozen status receipt verifier accepts
717760samples=717731raw-equal+29invalid-only. All29 full raw rows remain:
both valid bits0, candidate`1xx00101`, reference`00000101`, epoch11,
1198594347644..1198674347648fs. The candidate payload differs from prior
runs, and its driver origin remains unresolved. All eight valid-status bits
remain checked; neither raw217 equality nor the old strict failures is
reclassified as passing.

Original receipts retain44healthyblocks,12active-inputfaultcases,
two vendor-open quarantine cases and two reset recoveries. Actual
inverse-current/sticky-forward counters remain0. Registered preparing,
expected-cache and raw-bank boundary rows also remain0 in this R0 run.
No registered/D/S active proof follows from these baseline results.

## Scope and handoff

The added alignment passes this actual scheduler/guard sequence without
moving any old checker. It does not prove the precise prior simulator
process order or arbitrary asynchronous stimulus safety. The preserved8757
failure, strict217 mismatch and initial offline7PASS/5FAIL remain intact.

Archive: `hdl/library/starlink_pss_acquisition/evidence/extra-edge-actual-v1/`.
It retains full frozen sources, raw logs/warnings/timing, all receipts and
invalid-status rows, before/after inventories, complete original/extra CSVs
and saved WDB (losslessly compressed). The original project remains intact.
No further mode or physical experiment is authorized by this result.
