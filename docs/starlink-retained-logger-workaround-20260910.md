# Retained actual logger: narrowly frozen workaround

Source FW `d49ceb8b0f84f8ab3d4ec8233587dd9c81065b3e`, HDL
`b94909a6c15a2b99cd5cd0bcdc6d646d2a05c575`. This report covers offline
preparation, not the parent-owned subsequent full actual outcome.

Parent actual43908 passed the repaired declaration/startup boundary, admitted
F at934 and released reset at936, then encountered the simulator kernel crash
in the first conditional-string logging call at939. The runtime was not changed
in response to that crash. Parent minimal twelve-case actual XSim experiment
22575 then isolated the failure to all four conditional-string calls; eight
literal/explicit-if-else controls produced exact bytes. The same automatic task
and numeric arguments were used. All crash exits/partial CSVs remain preserved.

## Two logging sites, no DUT change

Only the input and raw-output call sites in `witness.svh` change from ternary
string arguments to explicit `if(actual_inverse)`/`else` calls with literal
stream names. The task body, format string, arguments, sampling location,
arithmetic checks and all runtime/control sources remain unchanged.

The new helper enforces a complete-source two-site inverse to original witness
SHA256 `3e0c8258c3bdb3a6005186ff17ec15547822e6d69e620b154bbc8582ea968d6a`.
The entire expanded bench similarly restores v3 SHA256
`713dac6ec03abea20a8899692f5312de89a2988df0dc1ef5e300d5ea30b2fb89`.
Missing/duplicate sites, swapped phase, changed arguments, format, task or checks
reject. The standalone reproducer and its test are included in the new closure,
but are not in the DUT compiled profile.

## Failure-marker correction

A separate parent parser-only counterexample showed that an appended actual
`FATAL_ERROR:` kernel message escaped the old word-boundary `fatal|error` regex.
The underscore prevented either word from matching. The only parser change
adds explicit `fatal_error` to that case-insensitive alternative. Exact real
message and mixed-case regressions reject otherwise complete logs. Numerical,
timing, identity, inventory and source gates are unchanged. The earlier real
crash was already rejected for incomplete inventory; no accepted actual result
is relabeled. The original accepted-mutant evidence remains in the tiny-repro
portable archive, SHA256
`4430a560aabe2d97554242c1ec0a42b2b037eb748d1d02450d71d5b0fc6eaf20`.

## Executed offline proof

Original15028 ended1:179PASS/1FAIL22.45s, retained at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-logger-final.sHt2txOb`.
Both full scripts and strict parsers passed and their complete77,953-row CSVs
already byte-matched. The extra simulation.log equality failed solely because
Icarus reports its source filename and `$finish` line: original_v3/bench.sv:506
versus literal_calls/bench.sv:508. The raw logs remain intact.

The approved narrow correction independently locates the unique literal
`$finish;` line in each bench, requires exactly one corresponding provenance
line at the identical fixed time512702882778fs, and permits only that exact
filename/line substitution. Every other log byte remains identical. There is
no general normalization or failure-line deletion.

Final original32708 terminal0: **180PASS23.00s**, retained at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-logger-final-v2.9tbmjlxR`.
Parent independent69282 terminal0:180PASS22.86s, all77 sources unchanged.
Exact five-file pytest scope (Python-B, sanitized environment, cache disabled,
unique recovery TMPDIR/basetemp and full log/XML):

```text
tests/test_starlink_retained_output_actual.py
tests/test_starlink_retained_output_actual_bundle.py
tests/test_starlink_retained_completion_declaration.py
tests/test_starlink_retained_logger_repro.py
tests/test_starlink_retained_logger_calls.py
```

Both complete scripts retain19 pairs/two aborted F prefixes and all original
receipts. Their CSV files directly byte-compare and match original v3 SHA256
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
The Icarus proof is not actual XSim throughput qualification.

## Frozen v4 bundle

`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-output-actual-prelaunch-logger-v4`
contains77 source files and80 receipt-bound files plus manifest. Manifest SHA256:
`eef29e37ca54241a3fc8cc664b07bfdb4b8948b72be4207e6a44953f7d9cbc38`.
Source signature:
`4666a75e528ba3be9960f393d20e38d1afe7a2ed4fce5f691b89f649d6d7bc13`.
Manifest bytes match the final test-produced bundle. Frozen resolved-base Python
CLI from `/` with `--live` passes. Relative to v3,67 common sources are unchanged,
six change and four are added. Runtime, clocks, profile, all eight goldens,
compiled list, task/format, recipe and ABI remain unchanged.

Parent exclusively owns subsequent actual execution and its evidence. There
is no additional agent vendor launch, hardware access, receiver promotion,
lower-clock approval or continuous native/canonical source claim here.
