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
