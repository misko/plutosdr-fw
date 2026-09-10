# Native60 standalone service: actual RTL simulation PASS

The one authorized corrected native60 run passed complete numerical, public
readback, source, lifecycle and integrity checks. Original handle75987 returned
terminal0 (final chunk a0cb6a); no retry or changes occurred during the run.
This is one healthy static-known-center native60 public-wrapper simulation,
not paired PSMA/PIL1/FFT, physical timing, RF accuracy, causal detection or
deployment qualification. Public bank60 admission remains disabled.

## Frozen inputs and invocation

Launch FW `0c49f441030c9507d1e1f7391a3b563cd13b5bb7`, HDL
`706ffb7b5b842409d8a8714c056203d8b5555034`. Only additive/test-boundary changes;
all native runtime RTL and original69 numerical files remain unchanged.
Prepared bundle `build/native60-budget-readback-prelaunch-v1`, SHA256
`bbcb423cf7d1f73bd6a6e7be3666aafe1eaa80414f7d99384ec5ad73c049ba83`.
91-source signature `8430b4e668a102ed794c82248b9ad509ec803a00f69097faa61cea1274a15798`.
Parent independently verified all162 bundle-file receipts,91 live/frozen
sources, original69/76/recipe, compile-only and575 offline tests before launch.

Exact invocation from the isolated high-rate60 worktree:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
 build/native60-budget-readback-prelaunch-v1/source_snapshot/tools/prepare_starlink_native60_budget.py \
 run build/native60-budget-readback-prelaunch-v1 \
 /tmp/starlink-bank-route.I50MDJ/main-native60-service-readback-v1 \
 --expected-bundle-sha bbcb423cf7d1f73bd6a6e7be3666aafe1eaa80414f7d99384ec5ad73c049ba83 \
 --authorize-native-service
```

The final preparation scope is exactly575 tests, comprising
319 native60 preparation/readback tests and unchanged256 numerical30/60 tests.
Own final behavioral run575 PASS20.06s, handle23651 terminal0, retained in
`build/native60-readback-tests-v2*`. A subsequent import-format-only lint fix
preceded freezing; parent independently tested the exact final source575
PASS19.95s at `/tmp/starlink-native60-readback-parent.LuaPUs` (handle34984).
Earlier319 PASS4.39s and all original preparation/failure artifacts are retained.

## Actual clock, source and admission evidence

Source oscillator first rising/falling edges were10,433,333/18,766,666fs.
Every half-period8,333,333fs and rising period16,666,666fs satisfied the frozen
1fs-resolution checks; control period10,000,000fs. This is measured simulator
cadence, not merely a RATE parameter. Source clock continued after valid/enable
stopped; the final256 control-cycle no-stale interval contained154 source edges.

All16,423 original nonperiodic CI16 source words and their consecutive indexes
`[34359735211,34359751634)` matched exactly, with uninterrupted strobe. No added
tail. Capture520 original samples `[34359740256,34359740776)`,264 original Q15
coefficients, center34359740384. Configuration completed at cycle2700 with public
ID50535354/ABI00010003/rate60/geometry0f8c1108/caps1d, generation60000001 and
Eh1073758594. Source log includes every input; capture log includes every slot,
original index/timestamp and CI16 word.

The low-register capture witness at cycle8284 held34359738559, with live offered
34359738560 (lag1 <=2). Completed low/high pair at8295 exactly matched that64-bit
witness and the retained snapshot, live34359738567 (lag8 <=31); read-return age
11 <=48 control cycles. No handshake-bound widening was used. Actual native
command admission occurred at8334, index34359738591, lead1664; trigger8282 to
handshake52 <=256 cycles. Actual index is inside the unchanged closed
`[34359738560,34359738720]`, lead inside[1535,1695]. Request60000520 and generation
60000001 are packet identities; visit60000052 is fixture context outside packet.

## Complete native service and independent tail drainage

All257 raw tuples (lags−128..128),241 qualification flags (−120..120), every
real/imaginary48-bit accumulator, Ex/Eh,96-bit power and saturation count matched
the immutable independent oracle. All257 per-tuple hold lengths were logged;
maximum hold11 <=16 cycles, with stable467-bit payload until handshake. Both
26-word public packet reads matched exactly, with32-cycle retained ownership
between reads and24-cycle public-release settle. AXI maximum7 <=24 cycles,
105 <=140 post-capture readout transactions. All configured health remained zero.

| Event | Control cycle | Cycles since final captured sample |
|---|---:|---:|
| Final captured sample | 11,974 | 0 |
| Original finite source disabled, compute still active | 30,072 | 18,098 |
| Result publication, raw249/qualified241 | 84,472 | 72,498 |
| Public result released, raw252/qualified241 | 85,261 | 73,287 |
| All257 raw drained, correlator/reducer/bridge idle | 86,616 | 74,642 |
|256-cycle no-stale observation complete | 86,872 | 74,898 |

Publication72,498 and full drain74,642 both satisfy the original84,000-cycle
limit; public release73,287 satisfies88,000. At ideal100MHz these are724.98,
746.42 and732.87microseconds respectively, simulated service times only. They
are not host execution benchmarks or physical Zynq timing results.

Eight unqualified raw tuples remained at publication. Three completed before
packet release; the final five completed afterward. Thus neither packet
publication nor release was treated as full job completion. All257 drained
before the exact256-cycle final no-stale observation. Source-off compute was
observed for56,544 configured control cycles (not coefficient-preparation work).
The source clock supplied34,080 further rising edges after source-off. Final
IRQ/result_available zero, engine/reducer/bridge idle, no new tuple/capture/
command and no health fault. Global watchdog160,000 cycles was not approached.

## Original evidence, integrity and portable inventory

Full raw run remains at
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-readback-v1`:
246 files/6,722,254 bytes. Compile and simulation exits0; compile log exactly0
bytes on this attempt, error/integrity_error null. All before/after frozen-source
and69 working-fixture receipts match. The source-snapshot result verifier was
also rerun successfully against retained logs, without rerunning native RTL.
Host/environment and Icarus/vvp binary SHA pins are retained in run receipts;
host `gauss`, Python3.11.16, Linux x86_64. No claimed host service benchmark.

Full246-file archive (including native.vvp and all frozen inputs):
`reports/experiments/20260910-native60-service-readback-v1.tgz`,1,814,229 bytes,
SHA `59a36a1b36bb05c9f0be992596080ecb998d12e391e2d03cdafa6d7944d7e3aa`.
It contains246 regular files and16 directories; `tar --compare` against the
original run tree passed. No evidence was removed. Every raw-file hash is in
`reports/experiments/20260910-native60-service-readback-v1.inventory.json`, SHA
`7cd65679521484aa8461bd12f062f469bee92f3bbe158d7ab3c06a0dd48fecd9`.

Key original receipts:

- simulation.log SHA `a9c0197bdb887fc8caaa2f062e788631a5701d8bfa909fef6a332c10131fc107`
- run-status.json SHA `d222ac7176c31013fa58910b093e4b1a8cab9bc15689b32198549bba0e2b0c3a`
- terminal.json SHA `ad5fddfe2fda252b8d976c1171745e88a8e8722002f3dc847f4e64e1df7f26f5`
- sources-after.json SHA `6d237c1fdb02705d8ac5ae59ebda54846d95f196e733841fd35f4623a3477d37`
- fixture-after.json SHA `f438caf599c47476ad0e971fe5b4492bdd790d9d0d7c5bc5315c0a86621f3990`

The original pre-command failure and print-only diagnostic remain separate,
unchanged archives/reports. Their cause was a bench condition applying the
real-handshake lower bound to delayed public telemetry; no native runtime or
golden changed. This successful correction does not erase those failed attempts.

Remaining scope: one static healthy upper60 native-only job, free result store,
bounded direct AXI, ideal clocks. No queued-load capacity, negative native60
epoch, paired coarse/PIL1 overlap, causal handoff, public bank60 admission,
60MS/s deployment, physical timing or RF-accuracy claim follows.
