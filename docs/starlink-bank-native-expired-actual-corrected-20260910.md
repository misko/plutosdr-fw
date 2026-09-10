# Expired native command: corrected actual175/200 runs pass

Both authorized corrected runs passed the exact negative command contract
while the unchanged coarse/map/pilot checks passed. The native request was
**rejected as late**, not admitted and not a healthy native visit. No numerical
edits, predicate changes or retries occurred between launch and both terminals.

| Run | Original handle | Terminal UTC | Simulation end |
| --- | --- | --- | --- |
| `bank-native-expired-175-corrected-v3` | 2476 | 2026-09-10 06:22:07 | 311310ns, exit0 |
| `bank-native-expired-200-corrected-v3` | 48117 | 2026-09-10 06:22:10 | 311310ns, exit0 |

Both handles were owned and polled to completion by this subagent. Sources were
clean frozen FW`b07e0419261db5d465328367b534a61d7ed234a3` /
HDL`1ece302ec9ea2dd1a6ccad713c75c4abfcc682b1`. Runs remain under
`hdl/library/starlink_pss_acquisition/build/`, with adjacent outer
`.vivado.log`/`.vivado.jou` files. This evidence stage changed no HDL, runner,
oracle, source, arithmetic, physical constraints or runtime integration.

## Actual expired request and public result absence

Both clocks observed the same exact source-index transaction:

| Event | Observed value |
| --- | --- |
| Request / coefficient generation | `15005202` / `15000002` |
| Center / timestamp | FIRST+520 =8589935096 |
| Intended capture start | FIRST+488 =8589935064 |
| Actual public submit | FIRST+620 =8589935196 |
| Actual sample-domain command handshake | FIRST+623 =8589935199 |
| Start minus next accepted index | −136 =`ffffffffffffff78` |
| Actual late / duplicate / overlap predicates | 1 / 0 / 0 |

The actual scheduler branch—not merely the intended host schedule—was late.
Exactly one public submit, wrapper handshake, FIFO acceptance pulse and
sample-domain handshake occurred. Rejected and late counters became1;
admitted, captured words, completed capture, packets and IRQ remained0. The
same-edge counter/ownership and unconditional no-work/fault assertions passed.
No captured candidate was admitted then aborted, and no native result was
injected or fabricated.

Two public atomic snapshots, generations1 and2, each read the31 frozen
address/value pairs in exact order. An independent postrun parser compared
all62 logged reads against both the immutable event JSON and register-word
file. Scheduler/engine/reducer/result counters matched; active coefficient
generation/energy remained`15000002`/1073742825. Public result status was
`1a000000`, available0 and IRQ0 after rejection and after coarse stop.
No unavailable0x54 packet-data read or0x58 release was issued. Such an empty
read is not a defined zero packet: the tracker has no qualified word-valid,
and the common AXI adapter can eventually return`0xdeaddead` timeout data.

The corrected configuration guard also passed: source_enable/strobe were
required known0 before configuration, only exact coefficient-preparation
states were allowed busy, and configured operation required IDLE/busy0.
Both actual public/sample handshakes required configured/source_enable/strobe
known1. Neither actual compiler log contains the former implicit-source_enable
declaration warning. The declaration-order repair remains negative-bench-only;
healthy base helpers and source timing are unchanged.

## Concurrent coarse and independent pilot

The bounded observation window opens at the public submit attempt and ends
four100MHz cycles after the observed sample rejection. Its measured witnesses:

| Witness | 175MHz | 200MHz |
| --- | --- | --- |
| Actual FFT RUN_JOB/core-active/nonfault fast edges | 49 | 57 |
| First fast edge after rejection also RUN_JOB | yes | yes |
| Pilot-DDC canonical input accepts while coarse/pilot active | 4 | 4 |

These are actual per-clock measurements, not lower-clock extrapolations or
guaranteed service bounds. There is deliberately **no native capture/compute
overlap** in this negative case: no native job may begin. The witnesses prove
that rejecting the expired request occurred alongside real coarse FFT service
and pilot input acceptance, not that every pipeline stage ran simultaneously.

Both benches checked894 exact coarse scores and447 exact public map words.
Each pilot stream had512 ordered words and2048 exact bytes, continuing beyond
coarse boundary stop. The independent postrun parser separately checked all512
logged pilot ordinal/newest-index/data tuples and the little-endian2048-byte
sink against the frozen independent oracle. Pilot SHA256 is
`3c754ff064c7fbfd4bcbe4560353f14fba0d2fd7cde68b5c4bba3a49681f8108`.
Coarse/map values were checked word-for-word by the running bench; they are
not individually printed in the raw log, so no independent postrun re-reading
of894 actual coarse words is claimed.

The inherited later invalid map release still deliberately produces joint
failed health while retaining terminal coordinates and pilot bytes. Its exact
late-fault marker passed; no generic fault exemption was added. The subsequent
minimum32-fast-edge FFT reset-held/no-restart quiescence check also passed.
Neither is a native-owned-capture gap/reset epoch; those remain separate work.

## Immutable evidence and limitations

Archive:`reports/experiments/20260910-bank-native-expired-actual-corrected-frozen.tgz`.
SHA256:`61290438624552f8a3af9a0d733150f0dfd3ac5b06fe79fc1ecba39216348707`.
Size4545814bytes;256 safe unique regular files, every member hash verified.
It retains both complete115-input snapshots, scope/IP receipts, generated FFT
wrappers, raw logs/journals, pilot files and WDBs. Companion
`20260910-bank-native-expired-actual-corrected-results.json` records all256
hashes,115-source hashes,62 register reads/run and exact terminal observations.

Both complete pre-run inventories match their postrun files and the reviewed
offline correction byte-for-byte, with no missing/extra files. All13 Python
runtime modules match the pinned FW blobs; all24 cohort files remain unchanged.
Fixture SHA is`aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81`;
event contract SHA is`680cdbdd674809de536a3323f99d74aa803174af650447cd816bd4ec7b6dfef7`.
Generated FFT wrapper SHA remains
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
Independent invocation of each frozen negative postprocessor passes as well.

The two first failures and diagnostic failure remain unchanged in their
separate387-file archive, SHA`a690d6d45308fd19c32093bb601c60bda8f5f949e9065651ad4e392c3f31ab2e`.
Their original failed outcomes are not relabelled. The303-test offline
correction gate and its120-file archive remain separate evidence.

This is additive test-only, actual-generated-core behavioral evidence at
original15MS/s with a static synthetic fixture and reduced447x2 map geometry.
It is not causal acquisition, source30/60 integration, RF accuracy, physical
timing, DMA/IIO deployment, production dwell/duration or full-receiver
qualification. No radio, PPU, physical build, primary worktree, remote push or
runtime promotion was touched. The full coarse/native/pilot requirements remain.
