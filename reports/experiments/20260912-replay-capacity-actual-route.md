# Replay capacity and cancellation partition — measured, NOT deployment-ready

Date: 2026-09-12. Firmware and HDL branch:
`codex/starlink-rx-only-do-not-merge-replay-capacity-buffer`.
Do not merge this firmware into main.

## Decision

Keep these as measured alternatives, not a receiver promotion. The local-fault
ring passes the complete inherited 82-case actual-FFT fault/reset/stall campaign
and 2,181 scoped regression tests. Eight additional evidence-recorder tests pass.
Its 175 MHz timing remains negative, and the overall route is not qualified.

The experiment starts from private replay FW
`7b2ba31b2c98ec0f97776e822b061be9b055c33c`, HDL
`e6f7bdfaf02efdd38b7ae8e5a3c83b5bd961802b`.
It does NOT incorporate the rejected product-local-framing candidate.
Current implementation source FW
`50f9811e79c9ab90d27d1c0af7f6f714ee61fdcb`, HDL
`39b08bf8cb06caca2013223bb14c0406bec9afac`.
The primary receiver HDL gitlink remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## What was built

1. Two-slot head/tail replay queue between the sealed forward FFT bank and the
   kernel consumer. Upstream capacity depends on local registered occupancy,
   not current downstream READY. One occupied slot supports simultaneous
   enqueue/dequeue; a full queue has one recovery bubble.
2. Alternating-slot ring with equivalent existing controls/owned payload.
   Wide slot writes no longer depend on downstream dequeue. The source can
   write private bytes on its cancellation edge; occupancy is purged and
   publication is vetoed immediately.
3. Additive local-fault output on that ring. Known current upstream cancellation
   still drives the complete FIFO fault, public-output suppression, sticky
   fault and occupancy purge. It is no longer unnecessarily echoed into the
   same-edge shared product/guard fault. Unknown cancellation, malformed
   controls, abort and sticky faults remain local faults. Both original
   actual publication predicates are unchanged.

The first queue added two modules to the parent's 41-module source inventory;
the ring has 45 and local-fault candidate 47. Each preserves all preceding
runtime source files byte-for-byte. These are source inventories, not claims
that all archived alternative modules instantiate in the synthesized netlist.

## Functional evidence and rejected runs

All healthy actual-FFT runs retain 64,512 exact numerical words across six
contexts. Service is 4,179 fast clocks, one more than the 4,178-clock parent,
against the unchanged 5,215-clock short-service limit. The CSV hash is
`7af9842c7bf50e27caaeef9e2161d221726e2d6ecdf9b94567b461d2f2ca4aed`.
The hash differs from the parent because cross-stream ordering changes with
the pipeline delay; the numerical audit compares the per-stream/key truth.

The component tests exercise 4,096 continuous words, 20,000 randomized cycles,
768 four-state control/occupancy combinations and both raw resets at all three
occupancies. Mutants for ready bypass, cancellation, storage corruption,
reset state, fault echo, unknown cancellation and sticky-fault loss are caught.
The additive local-fault port is checked while every original FIFO control and
owned word is compared cycle-for-cycle against the original ring.

Both initial layouts passed the 17-case targeted actual smoke, not the complete
campaign. The full original ring run completed all simulator boundary tasks,
but the strict post-audit REJECTED it: forward-private-status guard_delays was
zero. Its current cancellation feedback had bypassed the intended registered
diagnostic behavior. A simulator PASS label or Vivado exit zero does not
override this rejection.

The first local-fault runs were also REJECTED by the audit because the new
REPLAY_LOCAL_FAULT_PASS label contained the inherited LOCAL_FAULT_PASS token.
The version-2 observer uses REPLAY_CANCELLATION_PARTITION_PASS. Only the report
label/helper changed: no RTL behavior, inherited observer or acceptance
threshold changed. A dedicated coexistence test checks both strict parsers.

The version-2 full campaign passes all 82 inherited cases and fresh independent
re-audit, using the exact same 47 runtime files as the routed design:

- 850,309 cancellation-partition checks; 32 external-only cancellation edges.
- 28 delayed guard-fault edges, with both original current publication vetoes
  and next-edge registered cause/quarantine checked.
- 1,700,618 queue comparisons; 154 full cycles and 74,991 simultaneous refills.
- Seven cancelled private writes, all fenced; 12 private-only kernel takes,
  including five final words, all quarantined.
- Actual bank request toggles, reset/reuse, retained data and fresh recovery
  remain covered by the unchanged inherited campaign.

Auxiliary input/output/cancel counters are NOT a single global conservation
equation across resets and rejected-edge private writes. The per-edge
scoreboard checks healthy conservation and explicit purge boundaries.

Regression scope: exactly the prior 120 modules (2,151 tests), plus three new
modules (30 tests), passed in 139.26 s. Eight recorder tests passed separately.
An attempted whole-repository collection was rejected by three missing
historical evidence-file dependencies in the sparse worktree. We do not claim
a completely passing repository-wide suite. That failed XML is retained.

## Measured routing

Vivado 2022.2, xc7z010clg400-1, unchanged 100/175 MHz isolated route recipe;
no new timing exceptions. These are NOT full receiver board clocks/signoff.

| Variant | Overall WNS ns | TNS ns | Failing endpoints | Worst 175 MHz ns | LUT / FF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Private replay parent | -1.182 | -349.709 | 930 | -0.970 | 2756 / 5908 |
| Head/tail queue | -1.327 | -598.951 | 1177 | -1.244 | 2887 / 6149 |
| Alternating ring | -1.278 | -347.824 | 984 | -1.278 | 2956 / 6155 |
| Ring with local-fault partition | -1.334 | -452.620 | 1214 | -0.977 | 2902 / 6152 |

All three use 16 RAMB18 and 21 DSP in this isolated subsystem.
The latest route has 8,913 fully routed nets, zero routing errors, +0.035 ns
hold slack and +1.830 ns pulse slack, but setup still fails.

The head/tail wide enables fail at -1.115/-1.089 ns. The alternating ring
removes that dependency: +0.788/+0.836 ns initially. After local-fault
partitioning, physical placement gives +0.159/+0.010 ns for the same 115 used
payload enables per slot; the tiny margin is not a robust closure claim.

Latest measured endpoints: forward-position CE -0.366, kernel-next CE -0.850,
kernel history -0.118, ring count -0.132, ring read pointer -0.572, ring write
pointer -0.239, product publication -0.848, output publication -0.561 ns.
Descriptor and product/output occupancy paths remain positive.

The latest worst 175 MHz path is held engine metadata through preflight
comparison/preparation-fault reporting into a guard fault-reason register:
six logic levels, 6.686 ns, 82.053% routing. Kernel-next CE still traverses
reset release -> product-bank READY -> identity refill -> kernel capacity,
with 2,318 loads on the intermediate fast_running net.

Overall WNS is now the scalar fast_fault register to the first slow-domain
synchronizer stage. The isolated unconstrained clock-crossing report is NOT
a license to waive it: CDC topology, real board clocks and scoped constraints
must be independently qualified. There are still 114 unconstrained inputs
and 124 outputs in this isolated report. Same-domain violations remain even
if that crossing is eventually justified.

Initial capacity-endpoints-v1 incorrectly inferred FIFO presence from
current_design, which was design_1, and omitted queue endpoints. It is
retained as incomplete evidence. Version 2 explicitly requires FIFO endpoints;
the ring probe explicitly requires ring endpoints. No omitted-pin result is
used as queue timing proof.

Early routes deliberately carry exploratory_only=true and
complete_fault_campaign_verified=false. The latest full campaign was checked
subsequently against the same synthesis/runtime source. Its separate proof
does not rewrite the historical early-route receipt or establish board signoff.

## Next bounded experiment

Target the remaining downstream READY chain rather than adding more replay
input storage. The product identity stage currently permits same-edge nonfinal
refill based on product-bank READY; that feeds the kernel sequence enables.

Evaluate a local registered-capacity output stage, starting from the lean
private-replay baseline so the extra replay queue is not automatically retained.
One candidate is an existing single slot without same-edge refill: no new
payload storage, but potentially one accepted product every two clocks.
Another is a two-slot output-stage capacity boundary if the single-slot
throughput budget fails. Do not use a combinational READY bypass to conceal it.

The sealed forward FFT bank now makes that downstream processing elastic.
The old identity-stage comment forbidding gaps originated before that bank;
this is a hypothesis to test, not permission to drop results. Keep the
5,215-clock acceptance ceiling unchanged. Approximately one additional clock
per 512-word product suggests room in the 4,178-clock short benchmark, but
actual measured scheduling and sustained operation must decide.

Require exact sample/metadata ordering, no dropped/duplicated accepted words,
fault/reset/candidate expiry, independently checked actual final publication,
full inherited fault campaign and early routed endpoint comparison. Compare
service/resources/overall timing against the parent, not just the latest
experiment. Only a demonstrable improvement merits full-receiver integration.

## Deployment gates unchanged

Preserve native 60 MS/s fine search, independent 2.5 MS/s CI16 IIO inspection,
15/30/60 MS/s qualification, independent host GLRT comparison and the eight
high/low targets with 120 ms valid dwells over a 300 s source timeline.
Short actual-FFT simulation is not continuous RF/DDR/DMA/Ethernet validation.

Still open: complete receiver timing/CDC/reset at actual board clocks,
sustained scheduling, real 60 MS/s RX calibration, native-fine/inspection
transport, paired live detections, bounded scanner/replay consistency and
clean restart/rollback. Do not lower the board's shared 200 MHz IDELAY
reference casually to match the isolated 175 MHz experiment.

No radio access or PPU changes in these experiments. Deployment remains
serial-attested .18 canary (1040007c4a94000211000b009186843ef2), then outdoor
Ethernet-only .17 (104000bac4950008230026001b440a003a), through pinned,
reversible PPU. .14/.20/.21 excluded; .17 RX1 remains on its powered LNB.
Do not enable TX. Reusable PPU work may go to PPU main; firmware may not.

## Reproducible evidence

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/replay-capacity-buffer-worktree-v1`.
Runtime evidence root:
`/dev/shm/starlink-replay-capacity.MDfTXxjB`.

Latest main/synthesis snapshot:
`ba066d69c0b751953768a5c84aa49a4275be7adb22c66e8cd9b960cc9616db40`.
Auxiliary snapshot:
`d5cef9232db0f80bb5c9dc413531e5fa021d2be1dcc9470c9649650df6cb83e5`.
Synthesis DCP:
`34f118734e0e2b13f652755c64cd42994ec498db98076afbbfd9a155d3f25e28`.
Routed DCP:
`160d543864f1a14d31b3f81ae2250670bbc905b6c159e63fe9b4ac607f6de711`.

The curated archive retains all three measured alternatives, their frozen
prepared sources, actual numerical CSV/logs, synthesis and routed checkpoints,
corrected and incomplete endpoint probes, component artifacts, regression XML,
and the rejected qualification/marker attempts. Vivado caches/waveforms and
historical generated regression payloads are intentionally excluded.

Archive: `20260912-replay-capacity-evidence.tgz`, 32,815,927 bytes, 1,801 members.
SHA256:
`6ec2b1ccbc7cf028f230a69eb6a863f91919afe8837e8301499fae52e3162a2f`.
Every member, source hash, gzip CRC and stable archive identity was verified.
Stored under `reports/evidence/` on the experiment branch; the sparse
worktree need not materialize this large generated archive.
