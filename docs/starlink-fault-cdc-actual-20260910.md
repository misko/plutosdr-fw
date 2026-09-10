# Per-cause CDC C1: actual-core simulation result

The one authorized R1/D1/S1/C1, extras1,175 MHz,QUICK0 actual-core simulation
passed its frozen runner and independent receipt replay. This is simulation
equivalence evidence, **not physical CDC qualification or timing closure**.
No retry, C0 run, synthesis, route, radio operation, or runtime edit occurred.

Source authorization: FW `4d59ce832f82fd06b8c95a1b2c2461a6162ecdb6`,
HDL `597a8ab65ce9d4ee68b4ca0fe4a98ab48604beb7`; runtime remains the reviewed
`02de07cc7a6c241dd6cc8cf5b733037d89eac6bd` candidate. Prepared inventory
`9c81c43d9ed0bbc6cfba1d40074d11ec8cd94530fc9d7920de809bd6d68ce39c` stayed
unchanged. All48 before and after source checks passed.

## Original process and complete receipts

Original owned handle20091 exited0; post-integrity status0. Start
2026-09-10T10:47:42.315817530Z; end10:57:22.768161867Z; `/usr/bin/time`
wall580.44s, exit0. Actual elaboration recorded all seven explicit top options
and `--mt2`, using Vivado2022.2 with the reviewed SuSE loader environment.
The exact frozen runner printed original completion, original exact-receipt,
and new CDC-receipt markers. `$finish` occurred at3560734467751fs.

Independent frozen `verify_result` handle33930 exited0. It replayed the old
exact receipts, unchanged qualified-status policy and new strict CDC receipt.
The source of the scalar comparison is actual `dut.fast_fault`, with original
`slow_running` reset. The complete CDC terminal is:

```text
FAULT_CDC_ACTUAL_PASS enabled=1 checks=712146 stage0_high=8958 stage1_high=8686 reset_samples=4675 current_fault_edges=7882 final_fault_edges=115 private_core_reset_samples=4265 scalar_source=actual_fast_fault reference_reset=slow_running
```

These are sampled-edge observations, not event or reset-transition counts.
In particular115 means aggregate-fault observations while the kernel index
was511, not115 injected final faults;4265 means sampled core-reset-low while
the fast epoch remained running and faulted, not4265 independently tested
private resets. The unchanged independent active observer separately reports
exactly two active final fault edges. Both original extra-epoch benches report
exactly2 final faults,3 held-final stalls,2 one-sided resets and4 recoveries.

Both complete main CSVs are589950 lines and SHA
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
Both complete extra CSVs are33180 lines and SHA
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
All four match the immutable passing111 run exactly; the internal independent
reference remained dec20 R1/D0/S0, not111.

Qualified-status accounting:1246258 samples =953795 raw-equal +292463
invalid-only status differences. All216 other fields remained unconditional;
all8 status bits were checked whenever either valid was not exactly zero.
Every invalid-only row and both valid values are retained. The old terminal
explicitly says `original_raw_contract_pass=0`; this is not a raw217 pass.

Other unchanged receipts:780367 active checks,36 consumed identities,270
unused private scratch differences,99936 owned-stall edges,143 reset-owned
edges. Healthy blocks44, maximum nominal forward interval4548 cycles.
Registered scheduling retained8 fault/4 reset boundaries,106 completions;
preflight retained84 reason rows,12 active tuple corruptions,12 expected-cache
cases and84 raw-bank boundary rows. Forward-retirement checks1179897 retain
`inverse_current=0` and `sticky_forward=0`: this actual run does not establish
those corruption cases; their separate earlier fast tests remain the evidence.

## Warnings and lossless archive

Raw warnings are retained: IP-name length1; empty compiled-library path1;
forward-declared identifiers8; initialized non-net output declarations16;
the existing glbl top-parameter warning1. The C1 elaboration additionally
warned `[VRFC 10-8913]` that its generated `distributed_fast_fault.cause_sticky`
identifier is referenced before declaration and pretty-printed output may be
illegal. Simulation completed, but this does not establish synthesis support
or waive the warning; the source-specific physical gates remain necessary.

Raw run remains intact at
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1`.
Archive: `hdl/library/starlink_pss_acquisition/evidence/fault-cdc-actual-v1`.
Its91-member manifest SHA is
`e60f50a0c8e1f01f787f7ae67d7a2d83b4c1c5d04b3ad655c0eb011b021334cd`,
committed at HDL `c8321c4576d65c402d47bf8a3b6bdd66b90ce211`.
The read-only Git-object gate passed all91 members with exactly92 tracked
files; raw receipt is
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-terminal-git-object-audit-v1.log`.
An audit-output filename initially collided with the preceding offline audit;
the new receipt was moved to this distinct name and the deterministic offline
audit was reverified/restored. Neither archive, source, nor run artifact changed.
It contains all frozen sources/settings, source audits, actual process/time,
all terminal receipts, exact full logs/CSVs as gzip plus raw identities,
generated IP config/wrapper, and the full WDB as three portable gzip parts.
No monolithic oversized blob is tracked. Original WDB122136408 bytes SHA
`6814cf9dfab867e3715f1c55f74c3196f78711b64f6fabd7125e692763aaca3d`;
assembled gzip112102920 bytes SHA
`ae7d925a9baac23e13b65451c877a2b86966eb92ad0c3e465e7a0a84daed32af`.
The unchanged previously tested reconstruction helper reconstructed and
verified both exact identities in a fresh output directory, exit0. The
original project, raw files, local monolithic gzip and reconstructed copies
all remain available. No earlier failure or route evidence was modified.

Next authorization is offline-only source-specific physical preparation.
The old R/D/S adapter cannot silently select C: new preparation must admit
this exact successful C1 freeze, explicitly bind/read back R/D/S/C1111, and
retain unchanged100/175 constraints, IP factory, directives and two threads.
No actual synthesis or route is authorized by this result. The earlier
unqualified route and its open CDC-10 finding remain negative evidence until
a separately reviewed physical measurement establishes otherwise.
