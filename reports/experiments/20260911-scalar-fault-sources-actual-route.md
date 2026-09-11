# Scalar fault capture: CDC restored, timing still fails

DO NOT MERGE or deploy. Branch:
`codex/starlink-rx-only-do-not-merge-scalar-fault-sources`.
HDL `2a028e8edce646ed4079b9e61f1d0622cf3515db`;
FW implementation `f93d3f498` followed by whitespace-only recorder cleanup
`2942497573aa895df83b16f392fe5e757e57e1bc`.

The original single sticky-fault register and direct clock-domain crossing
are restored. Its input uses the previously checked nineteen-cause expression.
Only one of 22 runtime modules changes relative to the distributed experiment;
the actual-FFT bench, arithmetic, interfaces, clocks and synthesis recipe remain
unchanged. Fault capture stays on the original edge and public current-fault
vetoes remain in force. Unknown/unsupported configuration keeps the scalar
fallback. No timing exceptions or new latency were introduced.

## Verification

1035 regression tests pass in 117.43 s; the 18 component checks are included,
not counted again. The source-extracted scalar block passes 313297 clocked
four-state comparisons and rejects six reset/sticky/cause/context/fallback
mutants. Both actual-FFT campaigns pass, with all 64512 numerical rows and
service clocks `3663/3663/4929/11729/3663/3663` unchanged.

Sticky comparison covers 503565 main and 437626 auxiliary clocks, including
6957/2750 fault-present and 2922/2260 reset clocks. Actual asserted cause masks
remain 0x663ff/0x40fdd: groups 12, 15 and 16 have finite source-level coverage,
not integrated injection coverage. Existing summary overrides, held-final,
fault cancellation, reset and fresh-recovery tests remain unchanged and pass.

Read-only routed-netlist inspection requires a direct net from fast_fault_reg
to fast_fault_slow_reg[0], ASYNC_REG on both synchronizer stages and exclusive
first-stage fanout to stage 1. This passes, as do reset-request/ack/purge checks.
CDC inventory returns to nine CDC-3 and 208 CDC-15; the distributed candidate's
critical CDC-10 is absent. This is not whole-receiver CDC signoff.

## Physical comparison

| Metric | Earlier scalar | Distributed (rejected) | Flat-input scalar |
| --- | ---: | ---: | ---: |
| Global WNS (ns) | -1.331 | -2.514 | -1.283 |
| Same-island WNS (ns) | -1.189 | -2.120 | -1.219 |
| TNS (ns) | -277.204 | -678.141 | -255.361 |
| Setup failures | 526 | 1184 | 607 |
| LUT / FF | 2732 / 5798 | 2775 / 5809 | 2759 / 5795 |
| FFT → fault capture (ns) | -1.189 | +0.624 | -0.301 |
| Fault register(s) → island worst (ns) | -0.976 | -1.999 | -0.820 |

All 8478 nets route without errors; hold +0.058 ns and pulse +1.830 ns pass.
DSP/RAMB18 usage remains 21/15. The isolated recipe leaves 114 input and 124
output ports unqualified. Global worst is output metadata bit 9 across clock
domains. Same-island worst starts at epoch_barrier/fast_release_reg and ends
at joiner/kernel_rom/output_valid_reg through product fault/framing and commit
qualification: nine levels, 6.930 ns data delay, 77.3% routing. A derived
release net on this path has 2170 loads.

**No promotion.** Recovery from the distributed regression is not general
timing closure. Relative to the earlier scalar, same-domain slack and the
number of failing endpoints worsen. The earlier READY-absorption result is
also better overall (-1.245 ns WNS, -245.991 ns TNS, 453 failures).

## Next structural step and deployment gates

Evaluate a complete forward-return buffer with separate local capture and
replay controllers. Reserve storage before starting the real-time FFT, seal
only a correctly framed/identified block, then replay it into kernel/product
processing. Keep immediate public fault vetoes, reset invalidation and capture
timestamps. This targets the coupled capture/retirement/READY dependency;
its timing benefit is not yet demonstrated.

First inventory storage reuse and budget any extra payload RAM and replay
cycles. A conservative extra 512 clocks would make normal service roughly
4175 versus the 5215-clock coarse-arrival interval; this is a planning estimate,
not a sustained-throughput proof. Include final holds and reset/recovery in
the measured budget. Test faults at seal/replay, full/stalled banks, malformed
LAST/metadata, stale epochs and continuous arrivals before actual-FFT routing.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/real clocks, actual 60 MS/s calibration,
continuous RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans
remain open deployment gates. Then qualify pinned PPU/rollback on .18 before
.17 Ethernet-only deployment. No radios accessed; .14/.20/.21 excluded.
No PPU/main or primary HDL gitlink changes.

## Evidence

[Archive](20260911-scalar-fault-sources-evidence.tgz),
[read-back receipt](20260911-scalar-fault-sources-evidence.json):
33,553,375 bytes / 6371 members, SHA256
`0536c2571098b13df160abd6037bb146b9bb426f7ac7d0f6e18eaebba344f419`.
Includes frozen sources, tests, actual FFT logs/CSV, synthesis/routed checkpoints,
matched parent/candidate paths, reset/fault crossing inspections and reports.
The archived evidence recorder is the pre-whitespace-cleanup version in
`f93d3f498`; runtime and all evidence are unchanged by that cleanup.

Raw: `/dev/shm/starlink-scalar-fault.xuB1HWdl`.
Prepared SHA: `b7a4a2bc1d143a8d30d0207261de5a73dfc989550c30d65082bfc63f8e57abeb`.
Routed DCP SHA: `6c4db93d45da7b3df0f24c79a401be9874f549586fa4330c08540479d6a67b64`.
Parents: [distributed](20260911-distributed-sticky-fault-actual-route.md),
[earlier scalar](20260911-forward-final-commit-actual-route.md),
[READY absorption](20260911-ready-logic-absorption-actual-route.md).
