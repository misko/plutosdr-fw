# Retained-output actual startup failure — not qualified for deployment

## Verified language correction

Parent original97638 exits0:31 tests PASS in0.93s. Independent audit confirms
only the exact-file SystemVerilog selection and its runner tests changed;
69 of71 sources, the bench, profile and numerical vectors remain identical.
Both executed Tcl-stub ledgers select the exact27 compiled RTL/bench files;
generated FFT VHDL/IP is not reclassified. This is preparation evidence only.

Frozen FW: `2f8a57fb6295a4ea3559e60e27a8033010846040`.
Frozen HDL: `ac357cf1e954604e110ef27a654e14960c41ae7a`.
Manifest SHA256:
`3a0eb7872722b65764178c813ec96946e61ce0ac226c0202ea0a70d24e559eeb`.

## Actual execution

Parent original74560 exits1 after29.1615s, without timeout. Compilation and
elaboration succeed. The unchanged simulation assertion terminates at fast
cycle31 (174285723fs), state RESET1, before any RACT_ADMIT:

```
Fatal: composition health cycle=31 state=1 fault=1 cut=01 owner=00 f=01 i=01
```

Original-source and copied-source verification both exit0; no results.json
exists. This failure replaces neither the earlier compile failure nor the
passing offline tests. No numerical campaign completed.

Source review establishes that cutover reason bit0 covers unknown raw/reset/
input controls OR unknown admission/configuration/producer-closure controls.
The two result-guard bit0 faults can propagate from the shared external fault;
the log does not demonstrate three independent faults. The compiler warning
about completion_accept's implicit declaration before its explicit declaration
is a diagnostic candidate, not an established cause. Separate shadow counter
initializer warnings also need inspection before claiming coverage counts.

## Read-only saved-WDB investigation

Parent consumed four terminal read-only Vivado query handles:37220,34055,
17830,93614. None launched or advanced simulation; the WDB remains SHA256
`78543a4b8b3073f6080c8bd05f2b7819ee4de6bd8b974fd3a87b548d2e80b0de`.

The initial hierarchy assumption was wrong: Vivado exposes the escaped scope
`/tb/dut/\retained.island `, including its terminating space. A corrected direct
pattern query was also insufficient. The final query enumerates real HDL
objects and passes their returned names verbatim to get_value_database,
avoiding escaped-name pattern matching. It finds37 relevant objects, including
cutover controls and checker counters. All296 values at eight startup times
are `<Blank>`, not logical X or zero. The original WDB therefore supplies no
usable recorded history for this diagnosis. It cannot establish the fault's
exact triggering signal or the counters' initialization values.

Next action: prepare a source-identical, startup-only replay with explicit
logging of the required controls and counters before execution. Keep the
original assertion, reset behavior and numerical criteria unchanged. This is
diagnostic instrumentation, not a successful numerical qualification run.

## Preserved evidence and limits

Archive `20260910-retained-startup-parent.tgz`, SHA256
`aeeb353bfaa53b1d12a1b2312670c9669c6befa09e49631f114fd88f0044dc39`;
tar comparison against original files exits0. Includes the independent31-test
source/log/XML/audit, complete failed actual run and copied inputs/project/WDB,
and all four read-only query scripts/logs, including unsuccessful queries.
Excludes tool scratch `.Xil`, Python bytecode, and convenience `*current` links.

Recovery directories under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:
`actual-language-parent.jB1Pioe2`, `retained-actual-sv-parent.cKDdhubU`, and
`retained-startup-wdb-parent.qfbprVv0`.

No radio configuration, flash, PPU change, production HDL gitlink promotion,
synthesis or routing occurred. Actual FFT behavior, physical timing, complete
60MS/s receiver qualification, IIO comparison and deployment remain open.
