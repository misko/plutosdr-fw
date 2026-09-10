# Arithmetic monitor boundary: offline preparation only

**226 tests pass in22.73s; Ruff passes. No actual FFT retry was launched.**
The two original actual175 runs remain failed. Their immutable failure and
standalone force diagnosis are documented in
`starlink-bank-arithmetic-actual175-failure-diagnosis-20260910.md` and preserved
in FW`2547051646fd759b9b513b8d7f1e57e3673447c3`.

Source commits: FW`fc5e9e9ef13f8f5fd175a0e2c9b931181813285c`,
HDL`18aa1b6f58fe7abcf06672fccf6d93551174de54`.

## Exact seam and unchanged contracts

Each of the two119-bit `product_outputs` monitor tuples now binds exactly
`output_bin_index`, `output_block_start_index`, and `output_overflow` to
`dut.product.arithmetic` output registers. These are the same register boundary
observed by the original direct-core monitor. Every bit remains compared.
Input-ready and all other fields stay at the existing wrapper boundary.
The six hierarchical references are the entire bench delta.

The old shadow body, new elastic shadow body, comparison predicates, external
overflow/position/start force stimuli, event checks, original current/late fault
veto assertions, reset tests, numerical vectors, and cycle bounds are unchanged.
All eight runtime HDL files are byte-identical to failed-run HDL`5e4c2ad2`.
This is not an epoch mask, arithmetic change, or full-chain latency equivalence.
O1 still has its explicit additional token stage and original event-indexed
checks; the full historical R1 baseline CSV is still required for B0/O0.

The helper verifies exact reviewed wrapper/core hashes before preparation and
again when verifying a frozen launch. A modified wrapper transport assignment
cannot be hidden behind the register rebind, even if a manifest is rehashed.
Strict inverse restores the full original dec20 bench byte-for-byte.

## Sufficient future mismatch evidence

One runner hook selects a new frozen40-line custom simulation Tcl. It retains
the original top-level waveform setup and `run all`, while additionally logging
both full119-bit monitor vectors, reference output fields, ready/reset/flush/
ownership qualifiers, wrapper/inner outputs, and bank current-fault inputs.
It does not change any assertion or simulated state.

The script requires four monitor-vector objects, two reference-overflow objects,
and exactly one wrapper/inner/transport overflow object each; total selected
objects are capped at256. It writes an exclusive, non-overwriting signal-path
inventory. The results collector requires its unique marker and exact inventory
counts. These are offline source/mock-Tcl checks: actual future WDB content is
not yet qualified. The old actual WDBs lack the relevant internal histories.

## Executed offline checks and preserved attempts

The46 new checks cover the six-reference delta and unchanged runtime/shadows;
missing or excessive rebinding; changed transport wiring; four healthy O/B
monitor combinations with stalls/reset/flush; ten genuine arithmetic corruption
mutants across both O values (overflow, bin, start, I, Q); six unchanged real
guard/mailbox current/held-fault cases; diagnostic inventory/nonoverwrite/freeze
policy; and six analyses of the already recorded identical-source Xsim/Icarus
force cases. Arithmetic corruption still fails the full output comparator.

The guard/mailbox tests use the existing explicitly synthetic interface, **not
actual FFT**. The six force-receipt tests do not launch Xsim again. The original
180-test arithmetic/control/actual-preparation regression also passes.

Original new-suite handle3135 completed EXIT0. Raw logs/XML/cases are retained
at `/tmp/starlink-bank-arithmetic-monitor-offline-v2.eaHNUX`.
The earlier184-test run passed in20.28s but had one iterator deprecation and a
Ruff import-order failure. Its source snapshot and raw receipts are retained at
`/tmp/starlink-bank-arithmetic-monitor-offline-v1.62QX0m`; neither is erased or
relabeled as a clean lint pass. The final run includes the previously omitted36
unchanged regression tests and has no warning.

## Frozen175MHz preparations, no project or launch

Both directories below are under `hdl/library/starlink_pss_acquisition/build/`.
They contain44 frozen inputs each, including the new Tcl, both policy sources,
and the runtime Python import closure. Neither has a project or launch marker.

| Profile | Directory | Manifest SHA256 |
|---|---|---|
| R1/B0/O0 | `bank-arithmetic-actual-baseline175-monitor-prepared-v3` | `440e349ac6c245cec032e18b717dc52037ed7e0b53f777d984aee9c0e2b43b2f` |
| R1/B1/O1 | `bank-arithmetic-actual-candidate175-monitor-prepared-v3` | `6376f1fb2508f357933d4cb9cd9949d8da452d155a47084701aa29fb99df1954` |

Runner SHA`684f8e788f7a3550d85ccc30eb32a56b7b72a4c8067c2aa59513d416bd177eb9`;
diagnostic Tcl SHA`b55135b641f63fde966e6e3411f2dfa3cfe7a7f9bef44a40bf8e9f22bee1bf7d`.
The exact source lists/hashes and before-launch state are in
`reports/experiments/20260910-bank-arithmetic-monitor-preparation-v1.json`.
Its adjacent archive has8,295 safe unique regular files,44,993,952bytes, SHA256
`9b7ff3bf21f94aaaf59f31e21fc0b0f0ae326628e23049b51b874866cf202acc`.
Every archived member was reread and hash-verified. Both offline attempts,
frozen preparations, source snapshots, and packaging script are included.

Any actual retry requires separate source-specific approval. This preparation
does not qualify bank throughput, scorer RTL, physical timing, source15/30/60
native fine, independent2.5MS/s pilot, RF accuracy, or deployment. The complete
receiver objective and .18-before-.17 ordering remain unchanged.
