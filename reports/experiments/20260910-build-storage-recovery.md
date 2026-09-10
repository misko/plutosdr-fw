# Build storage recovery — 2026-09-10

Scope: the original paired FPGA PSS scanner, on
`codex/starlink-rx-only-do-not-merge`. No radio access, firmware flash, PPU
change, or runtime promotion is part of this recovery.

## Interrupted runs remain failures

- ROM actual session 23845 terminated with exit 1 after the waveform writer
  reported `Disk quota exceeded`. Its candidate/reference CSVs match each
  other and the passing C1 prefixes, but end mid-line at epoch 160. Extra
  CSVs are absent. The frozen result verifier rejects this incomplete run.
  Original `after.sha256`, `time.txt`, and `end-utc.txt` are empty and must
  remain so. Fresh read-only source hashes matching the original manifest
  do not repair the failed stored after-audit or establish a completed run.
- Parent late-settle test session 63525 terminated with exit 120 during the
  same storage incident. Its partial log and empty JUnit XML are retained;
  this is not an independent 694-test pass.
- L1 synthesis session 57050 completed successfully before the incident.
  Its agent confirmed that routing had **not** launched, with no route
  process handle. Route launch and new archive writes were paused.

## Storage evidence and bounded relocation

Read-only checks showed `/tmp` mounted as tmpfs with `usrquota`. Aggregate
space still showed 12 GiB available and approximately 119,000 free inodes,
so aggregate free space did not prevent the observed per-user quota errors.
The root filesystem had 55 GiB available. No claim is made here about the
exact block-versus-inode quota limit.

No Vivado, xsim, or pytest process was present in the process snapshot taken
before relocation. Three root-owned, terminal pytest directories were moved
without clobbering into the newly created directory:

`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`

| Directory (formerly directly under `/tmp`) | Terminal evidence | Before/after canonical tar SHA-256 |
| --- | --- | --- |
| `starlink-late60-settle-parent.B4sCiQgs` | 63525: exit 120, quota failure | `17ae7cb2fcdc65d8eaa8316051fcf29ab1e65d6d3b61184b84c7d3b33dd9d168` |
| `starlink-highrate60-late-parent.4MaUmktU` | 53185: 681 passed | `3d85ed2af87042773f63b417512aac8f3a534422fd136724983d8ee1d738dd9e` |
| `starlink-local-schedule-parent.BDQZlu7W` | 98004: 188 passed | `2f0a45592d85dad7e72e3e8669bb8e38d676509c6a32d814474ecee162a7e306` |

Each digest was independently obtained before and after the move with
`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf -`
over the complete directory, piped to `sha256sum`. This includes regular
file bytes, relative membership, permissions and symlink targets; timestamps
and ownership are deliberately normalized. All three digests matched.
No evidence was discarded. Earlier reports' `/tmp` locations for these
three directories now resolve through the relocation recorded here.
Unrelated and agent-owned original run directories were not moved.

After relocation, `/tmp` showed 13 GiB available and the root filesystem
54 GiB. New large build outputs, archive staging, and subprocess temporary
directories are assigned unique paths under the non-`/tmp` recovery parent.
Only bounded completed publication parts and small worktree changes may
return to the isolated `/tmp` worktrees.

## Resumption gates

- Parent independent late-settle repeat 64537 launched with a new, previously
  absent pytest base directory, cache disabled, Python bytecode disabled,
  and `TMPDIR` under `late-settle-parent.26zBTKKN` in the recovery parent.
  Log and JUnit XML are retained there. Original session 64537 subsequently
  terminated with exit 0: **694 passed in 14.62 seconds**. Log SHA-256
  `1a51b1946ba5362b4dd76e4a71872d58182ebeb73ff91493734bab6144bc74c8`;
  XML `76095901c9bbd1115e09204b9a3617108a6032543f892f3d9e51b3c2e4f8864f`.
  This is an offline contract/model/compile test pass, not a replacement
  vendor simulation or a native hardware result.
- The L1 agent may perform the previously approved one-shot route of DCP
  `a6a8e404b90924bb538a0da2ae7be7fc9ebc9e0c323b8f1a17661b4550648242`
  with unchanged Tcl
  `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`,
  using new non-`/tmp` outputs. No timing exceptions or retries are authorized.
- ROM failure archival and an exact-source, non-`/tmp` successor proposal
  may proceed. A replacement actual simulation is not yet authorized.
- Corrected late-settle packaging and a non-`/tmp` successor proposal may
  proceed. A replacement vendor run is not yet authorized.

This recovery changes storage placement, not RTL, acceptance thresholds,
sample-rate requirements, or deployment gates.

## First resumed physical result: L1 still fails setup

Original route session 30536 terminated with tool/owner exit 0, one completion
marker and no owner errors, at 12:49:15.078927 UTC after 74.518 seconds.
The parent read its owner script, original receipt and critical paths, then
independently verified both input hashes and all 15 complete output products.
Owner directory: `local-admission-route-v1.EzXzzuNB` under the recovery parent.
All original inputs and outputs are retained. This is a successful diagnostic
execution, **not** successful timing closure.

- Global and island-175 setup WNS: **-1.549 ns**, versus baseline -1.341 ns.
- Global TNS: -389.428 ns, 541 failing endpoints; island TNS -305.523 ns,
  413 failing endpoints. Hold +0.058 ns, no hold failures.
- Worst path: `registered_scheduling.held_phase_reg_replica_1/C` through
  input-guard identity/current-fault logic to
  `result_guard/fault_reasons_reg[0]/D`; 6.925 ns data delay, comprising
  1.477 ns logic and 5.448 ns routing, eight logic levels.
- A second near-critical path (-1.510 ns) goes from result descriptor through
  output-bank metadata/fault logic to the registered admission receipt.
- Routed checkpoint SHA-256:
  `8a20a37373e03b12f8546dad6762ac879a02b1eb94ed815fce4790644803b3d7`.

L1 is not promoted. Review now targets the coupled inter-module fault/admission
cones, while the independent ROM-prefetch experiment remains separately gated.
External I/O, CDC and full-receiver qualification remain outstanding.

## Corrected late60 actual: passed in a fresh run

After parent review of the complete frozen runner, the independent 694-test
pass, and the relocated bundle's unchanged admission, exactly one corrected
vendor simulation was authorized. Original session **2011** terminated with
exit 0; Vivado exited at 12:54:29 UTC. Frozen `run_status.txt` records
`run_tcl_exit=0 integrity_exit=0`. The parent separately ran the frozen result
verifier from `/` and obtained `HIGH_RATE60_LATE_SIMULATION_VERIFIED`.

Run directory under the recovery parent:
`late60-settle-agent.7cjlYh/main-high-rate60-bank175-late447-settle-v1`.

The first audit now starts at cycle 13566 after handshake cycle 13558, meeting
the original eight-label bound. The second remains 32423 after source-off
32415. All 62 public register reads match. The command is correctly rejected
as late (source index 34359740319, lead -64), with zero native capture, raw
results, qualified results, packet reads, result publication or IRQ. Coarse
processing retains its exact 894 scores/447 map words and independent pilot
512 CI16 samples. The checked continuous segment remains 13,312 samples at
the simulated 60 MS/s clock. After rejection, 1,536 actual FFT forward
transfers and 2,353 pilot accepts show that those paths continue operating.

The parent independently rehashed all **672 raw files / 55,835,869 bytes**,
both external logs and all 119 live source files from the post-audit inventory.
The original, relocated and run-copied bundle remain
`79febd5abe231065f9fc77abd7c587104e4608ffd8eae40ebd5b4f20a6ac1043`;
generated FFT wrapper before/after remains
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.

This proves expected-expiry handling alongside healthy coarse/pilot processing
in the reduced, ideal-clock simulation. It is not a healthy native job,
causal acquisition, physical clock, Ethernet or RF qualification. Original
88460 stays failed; it was not relabeled by the corrected run.

## ROM successor launched; no result yet

Original failure 23845 was preserved in HDL commit
`04a2680b90a68efd53ab932748a54f401939eef0`, manifest
`a12ac3ce04e0644cfe2a5460354091992500ddcc0e68106b3f01d75021ac6786`.
The parent verified all 126 payload members directly from Git and read the
failure report, including original empty receipts and partial CSV/WDB limits.

Parent then checked all 56 relocated source hashes, external manifest
`6f5eddb99510e869bbe65548acc6ed64cd76bd98908aacfcd6e1c0361ccbe4ae`,
unchanged runner `9f198abf60d9119eae2ef565ae3d65b64104f93ce5f1b5be4b2e89776dd3deed`,
and complete owner-script inverse with only five base-path substitutions.
Frozen source-specific admission from `/` passes R/D/S/C/K/M=1, extras=1,
175 MHz, QUICK=0. No RTL, numerical gate, or clock change was made.

Exactly one successor session **10102** launched at
12:55:57.787981380 UTC under recovery directory
`rom-relocated-actual-v2.CWJkzwEi`, with a writable non-`/tmp` TMPDIR and
52 GiB disk headroom at preflight. Its agent owns the original process until
terminal. All complete numerical/fault/ROM gates, stored before/after hash
equality and persisted receipts remain mandatory; no result is claimed here.

## Reviewed publications

Successful original pushes, all to experimental do-not-merge branches:

- Primary firmware journal: `2bd6ab1e7` (before this appended update).
- Arithmetic firmware: `69e328325247a1355691cc88e4e8990d1c18ef05`.
  Parent verified committed preparation/synthesis/route archives with
  1,701 / 144 / 45 exact members respectively.
- Corrected late-settle preparation: firmware
  `9b67d3db938cbbb5aec42041a10a906464282d3f`, HDL
  `ecbb3712965ff39b144b5adf84a2a262c6c53dff`. Parent verified all 405 committed
  archive members, including 404 payload hash/length receipts.
- ROM failed-run preservation: firmware
  `2a84004109c9d12f2cb572f6333b8d420fecf8e0`, HDL `04a2680b9` above.

No firmware-main update, primary runtime-gitlink promotion, PPU change or radio
operation followed any of these publications.
