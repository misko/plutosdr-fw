# Bank-owned coarse PSS and independent pilot: paired digital replay

Both reduced map geometries pass with the real bank-owned FFT at175/200 MHz
and the existing shared FFT at200 MHz. The same digital CI16 samples feed the
actual acquisition shell, sample CDC, canonical tap, PSS map/PSMA interface and
PIL1 filtering/capture path. Every captured pilot byte matches the independent
integer filtering oracle. No production RTL, AXI receiver profile, arithmetic,
radio or PPU source changed in this step.

The test selector is a child `defparam` in the bench, just like its reduced map
geometry. It is deliberately not a new advertised receiver capability.
Initial tested HDL `56141715b3ef10305eabea7dad57b25eddf8708d`, FW `5132b5282`;
the last two initial runs additionally include the unrelated additive lifecycle
bench merge `9d9299914798af03dc9311c552548a2d199f2e80`. Their frozen paired
sources are unchanged. All six initial runs completed with verified exit0.

## Executed observations

| Engine / FFT clock | Map | Exact admitted scores / map words | Pilot bytes | Initial / hardened exit0 UTC |
| --- | --- | ---: | ---: | --- |
| Bank175 |447x2|894 /447|2048|02:20:14 /02:25:53|
| Bank175 |343x2|686 /343|2048|02:20:15 /02:25:52|
| Bank200 |447x2|894 /447|2048|02:21:32 /02:26:46|
| Shared200 |447x2|894 /447|2048|02:21:33 /02:26:49|
| Bank200 |343x2|686 /343|2048|02:22:50 /02:26:48|
| Shared200 |343x2|686 /343|2048|02:22:52 /02:26:50|

Each run uses 4,096 source words at15 MS/s, a100 MHz control/processing clock,
512 fully supported CI16 pilot words at2.5 MS/s, and the unchanged seven PSS
fixtures. The signed16 shell input is not a physical AD9361 formatting test.
The explicit768-sample pilot pre-roll and configuration pause are retained;
this is not a continuous hop/retune proof.

The bank forward-start witness observes actual core VALID/READY on `fft_clk`,
qualified by direction, position0 and the original full block coordinate.
Source-bank capture is not substituted for core execution. At healthy stop,
the447 case has894 produced/admitted scores, FIFO0 and an unfinished third
inverse. The343 case has687 produced but only686 map-admitted scores, FIFO203;
the extra visible tail score is still numerically checked, not silently admitted.
Residue239 matches the production tile's transform-boundary residue, not its
20,000x64 geometry, duration or capacity.

All map words are read/released through actual PSMA AXI-Lite. The source and
pilot continue after the PSS stop, while map counts and terminal coordinates
remain fixed. PIL1 AXIS backpressure, IQ/ordinal/newest-index/support/visit,
512-word snapshot counts, clipping and health are checked. The runner compares
the actual sink file against independent oracle bytes, not captured RTL output
relabelled as a golden. An independent agent also recomputed the frozen pilot
oracle and original shared1,406-sample input in memory for both175 runs.

A real invalid map-release after completed capture changes joint terminal health
to failed while preserving terminal coordinates and already captured pilot bytes.
It is not a fault injected during active pilot delivery or native refinement.

## Review hardening

The initial six passing runs are retained unchanged. Review identified three
test gaps: fast-domain teardown was inferred only from slow pipeline state,
general health checks were disabled during expected late bridge misuse, and
the447 runner did not require exactly one stop-tail receipt.

HDL `dbe744c0` / FW `6941dd36a` add a bounded actual FFT-clock witness: after
eight clocks of local pipeline teardown, fast-running/core-reset/config/input/
output-valid must remain inactive, including through the late-fault case. At
least32 such clocks are required before PASS. The one-picosecond post-edge
observation avoids NBA races; this is not a physical reset/CDC guarantee.
General health checks now remain enabled, permitting only the expected single
bridge-release count; late fault must not restart either branch, change admitted
counts or republish a map. Both geometries require exactly one stop-tail receipt.

All six strengthened runs pass both geometries, including the new quiescence
receipt for all four bank runs. All six source inventories and actual/expected
pilot byte comparisons were independently rechecked. Policy tests now pass122;
combined lifecycle/paired/PSMA/phase/clock
policies pass292. One initial combined-test command named a nonexistent clock
test file and collected nothing; the corrected command used
`tests/test_starlink_bank_clock_policy.py`. This was not an RTL failure.

## Evidence and open gates

Initial six-run archive: `20260910-bank-paired-pilot-replay.tgz`, SHA-256
`6fe88dd6d34ce4693270f1cfc4e15fb1140b35c286645442b030427760eb8626`.
It retains complete logs, source hashes, frozen RTL/helpers/vectors and actual
pilot bytes; generated vendor IP and firmware binaries are excluded. All six
source-hash inventories and independent byte comparisons were rechecked by root.
Every actual pilot file has SHA-256
`9ca24563bda3a3df6a0f780f3eb976eaac044d97ce752277b3781ba95942d1bd`.

The strengthened six-run archive is
`20260910-bank-paired-pilot-hardened-replay.tgz`, SHA-256
`1c49f1fd9919863a9d41a114bc4af5c7ce2ecdee6a4b5f53b222cd88a8d13623`.
It contains the same artifact categories for v2, without overwriting v1.
Each run's `scope.txt` identifies the complete frozen input inventory. Replay
with Vivado2022.2 using `simulate_paired_realtime_psma_stop.tcl` and arguments
`NEW_OUTPUT SCORE_DIRECTORY PILOT_ORACLE_DIRECTORY 447x2 1 175`; choose343x2
with its matching oracle receipt, or200 for the alternate bank clock. Omit the
last two arguments for shared200. The runner refuses existing output paths.

The independently completed lifecycle archive is
`20260910-bank-map-lifecycle.tgz`, SHA-256
`e8f3c1771e5a67067a1abba2f7d62b8eb813f5c1456cdc0a65b005ee0e8052fd`.
It retains the report, tests, frozen sources and both-run logs selected from the
101-hash receipt inventory; generated vendor wrapper files are excluded, with
their configuration/hash receipts retained. Original full artifacts remain in
the lifecycle worktree. No failed or incomplete run was erased.

Still required: production map capacity and120 ms acquisition policy, active
clock/reset/fault coverage across the complete composition, native15/30/60 fine
handoff, DMA/IIO delivery, whole-receiver timing/CDC/board-I/O closure and actual
RX calibration. Then reversible exact-serial `.18` qualification precedes
Ethernet/PPU `.17` deployment. No RF detection, timing accuracy, live throughput
or deployed60 MS/s fine search is established by these bounded digital tests.
