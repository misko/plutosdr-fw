# Actual-FFT preparation: independent ledger timing counterexamples

The draft result parser accepts two deliberately altered timing records in a
saved scripted replay. This is a verification gap to fix before authorizing the
actual FFT run, not an observed RTL or vendor failure. No vendor process or
radio was started. The original 415-test sources and results remain unchanged.

Parent read the complete draft derivation helper, physical-interface witness,
context scheduler and 170-line result parser. Its every-row numerical checks
are useful, but checking that a timestamp lies on the clock grid does not
establish that the sample occurred at the corresponding job's recorded event.

## Executed evidence

An independent parser-only probe loads the saved `script-v1` log and CSV:

1. Unchanged replay: accepted, 77953 numerical records.
2. Change only first `rawF` record (CSV data index1468): increment `fast` by one
   and `time_fs` by5714286. This preserves the fast clock grid but contradicts
   the unchanged job's first-output timestamp. Incorrectly accepted.
3. From the original CSV, increment the same record's `slow` counter by1000000.
   Its original timestamp and all other fields remain unchanged. Incorrectly
   accepted because the draft only requires the slow counter to be positive.

Probe exits0 after preserving all three outcomes and verifying its three
imported source files unchanged. Exit0 means the probe completed, not that
either altered ledger is valid. These are mutations of saved data; no HDL
simulation was rerun and no numerical golden was changed.

Parser SHA256:
`ce679dcd2dad378cf72a7474b1b4cf30dde55fb19be07f8c03cd81721407fa30`.
Derivation helper SHA256:
`b39d609ce6b6835f6922fd8b76147e51aaea657c1b14357f86d96826539330ab`.
Original helper SHA256:
`0066ae35105d57dfd3e7c924e036c4d518102853c6eb8ecde1c254ad9c2e3488`.

The owner has the exact counterexamples. Before the actual-core gate, join
numerical records to their context/job lifetime and physical first/final
events. Validate slow-edge counts against clock/pause observations, or clearly
leave that coordinate unqualified; do not claim the current check proves it.
Retain both malformed-ledger cases as rejection regressions.

Archive `20260910-actual-ledger-time-parent.tgz`: 4956895 bytes, SHA256
`479adf9ab1cc38a05ddd3dc2460806243f721b776bfcc0b360f6d6f37f82c66e`.
Contains probe, three imported-source snapshots, original log/CSV, complete
derived CSVs and result JSON. Archive comparison exits0.
Recovery `actual-ledger-time-parent.dqaOlckA` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
