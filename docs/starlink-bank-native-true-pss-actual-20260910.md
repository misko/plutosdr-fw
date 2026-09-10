# Synthetic520 concurrent coarse/native/pilot: two actual-core runs

Both authorized first attempts passed the complete actual-core runner with
exit0:175 MHz and200 MHz FFT, true original15 MHz sample clock, independent
100 MHz AXI/coarse clock. No retries, numerical edits, acceptance changes or
bench/helper edits occurred. This demonstrates bounded behavioral RTL
concurrency and exact arithmetic for a static synthetic PSS, **not causal
acquisition, physical timing, RF lock/accuracy, or production operation**.

## Frozen scope

Both runs used FW`c42ebde91507fa8ad9665e09709bd4ff926fe4ac` and
HDL`5ad9ba4a2ae7f196cbd44066eec725090cd76cea`, with clean worktrees before
launch. The explicit profile was`520-pss`, request`15005201`, coefficient
generation`15000002`. The immutable fixture receipt remains
`aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81`.
The source overlay, complete independently generated vectors, original-source
identity checks and offline244-test evidence are preserved in
`starlink-bank-native-true-pss-offline-20260910.md`; that earlier offline report
and archive are unchanged historical evidence.

Worktree root:
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-native-paired`.
Actual run directories under`hdl/library/starlink_pss_acquisition/build/`:

| Run | Original process handle | Terminal UTC | FFT capture overlap |
| --- | --- | --- | --- |
| `bank-native-true-pss520-175-v1` | 53217 | 2026-09-10 05:19:11, exit0 | 319 fast clocks |
| `bank-native-true-pss520-200-v1` | 88546 | 2026-09-10 05:19:13, exit0 | 366 fast clocks |

Both original handles were polled and consumed by this task, not restarted.
The invocation explicitly supplied repository Python through
`STARLINK_NATIVE_PYTHON=/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python`
and the required Vivado2022.2 library path. The hardened runner cleared the
Vivado Python/loader environment for independent C-model/oracle preflight,
used its complete12-module dependency freeze, then invoked actual generated
XFFT simulation with`general.maxThreads=2` and xelab`--mt 2`.

## Exact checks observed at both clocks

Each run consumed the same4096 original-rate source words (768 prehistory,
1406 numeric source including only the new66-word overlay, unchanged tail).
All existing source continuity, source-index, timestamp, epoch, configuration
pause and command-deadline checks remained enabled. Native injection was0,
the DSP reducer was enabled, and configuration/command/packet reads used
public AXI rather than hierarchical writes.

The native result was exactly26 words, read twice for52 exact public word
reads, retained across coarse boundary stop and then released. All130 capture
words matched the same raw source/index/timestamp. The independent golden
winner was0 with Re=Ex=Eh=1073742825, Im=0, power1152923654238980625. Actual
packet fields, coefficient/request identities, lag and timestamps matched
that complete independent packet byte-for-byte. The exact packet appears in
each raw log and the machine-readable results receipt. This is a synthetic
injected-PSS arithmetic result, not a measured radio timing lock.

Both runs checked894 ordered coarse scores and447 public map words against
the new independent goldens, plus512 pilot output words and2048 exact AXIS
bytes. The pilot continued after coarse stop. The stop ticket, terminal
coordinates, map ownership, native packet retention and pilot healthy
snapshot all passed. The map is two447-score frames; do not relabel this
as all1341 offline scores replayed through the selected paired RTL output.

The inherited late invalid coarse-map release then deliberately changed
joint health to failed while retaining terminal coordinates and pilot bytes;
the exact late-fault marker and at least32 fast-clock FFT-reset quiescence
passed. This does **not** exercise a native expired command, native capture
gap, FFT fault during native capture or a new recovery epoch. Those combined
negative cases remain separate work.

## Observed command lead and concurrent ownership

At both clocks the sample-domain native admission was index8589934602
(`FIRST+26`). Capture started8589935064 (`FIRST+488`) and contained130
words through`FIRST+617`. The observed lead was461 original source samples,
with deadline8589934704 (`FIRST+128`) and the strict64-sample minimum still
enforced. No sample-counter compensation, native-gap suppression or pause
inside the owned capture was used.

Capture first/last times were116835.433/125435.433 ns. The first actual forward
FFT input occurred at123615.592 ns for175 MHz and123608.800 ns for200 MHz,
both at source index8589935166 (`FIRST+590`). This includes the real outer
512-word input-bank fill and ownership handoff, not an ideal one-sample/clock
FFT assumption. Capture/FFT overlap was newly observed at319/366 fast clocks
for this exact true-PSS fixture, not extrapolated from the previous arithmetic
fixture. Native compute overlapping coarse-active plus pilot-DDC accepted
canonical input yielded842 witnesses at each clock. That counter is not a
count of2.5 MS/s pilot outputs or proof that every stage computed simultaneously.

The healthy-plus-late-fault bench finished at311240 ns at both clocks. These
short runs do not establish continuous300s operation, a worst-case service
bound, robust lower-clock capacity, or a physically achieved clock. No product
RTL, hardware banks, resource constraints or physical implementation changed.

## Provenance and archive

Each actual run froze108 source/vector/policy/helper files before project
creation. The pre-run SHA inventory was compared against the complete
post-run file inventory and hashes: all108 remained identical, with no missing
or extra file. The entire frozen inventory also byte-matches between clocks.
All24 fixture files and12 distinct Python runtime dependency files match the
approved cohort and its dependency hashes. Unlike the earlier arithmetic520
runs, these runs include the package initializer/transitive dependency freeze
before execution; no postrun supplement is used to imply missing pre-run proof.

Both generated FFT wrapper hashes are the unchanged
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
Both actual pilot-byte hashes are
`3c754ff064c7fbfd4bcbe4560353f14fba0d2fd7cde68b5c4bba3a49681f8108`.
The coefficient-file hash remains
`ca06f7fbabbb1566a420d0409c2dab3785bd57f219a10fb7f66ca381c6069488`;
the exact new native packet-file hash remains
`f8488f2393a08d17e57d8d1ec0e59b1369f0357de37934c6ed0dec66778a9699`.

The archive is
`reports/experiments/20260910-bank-native-true-pss-actual-frozen.tgz`, SHA256
`30f26c1925c96b8f912b1d13ab62787fed99214ec67c4204c42b8706417bf8db`.
It contains238 safe unique regular-file members: both complete108-file frozen
inventories, outer Vivado logs/journals, original compile/elaboration/simulation
logs, actual pilot binaries, scope/IP receipts and generated FFT wrappers.
No proprietary C-model library is included. All238 archive members were
hash-checked against the recorded evidence. All original input files and old
447/520 attempts remain untouched.

Machine-readable inventory, complete packets, original handles, exact terminal
markers and per-artifact hashes:
`reports/experiments/20260910-bank-native-true-pss-actual-results.json`.
After both terminal exits, the exact frozen native and paired Tcl postprocessors
were independently rerun read-only against each original simulation log and
pilot binary:PASS. A separate ordered512-word pilot/newest-index audit passed.
No apparent early PASS was used without the terminal checks or late-failure
scan. The existing offline policy tests already cover late FAIL/FAULT/Fatal/
ERROR and missing/duplicate/wrong profile markers; no helper changed during
or after these runs.

## Remaining boundaries

This first concurrent true-PSS fixture remains a prearranged anchor, not a
causal coarse-to-fine command path. Native expiry/gap/reset and FFT-fault
concurrent epochs are not implemented by this stage. Original30/60 MS/s
native source retention and rate-conditioned coarse kernels/public interface
guards, independent2.5 MS/s pilot IIO, receiver timing/CDC/external delays,
RF accuracy, `.18` before`.17`, and eight targets/120 ms dwells/300s remain
required. No physical work, radios, PPU, primary edits, pushes or runtime
promotion occurred here.
