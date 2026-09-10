# Expired native profile: first actual runs failed during configuration

Both authorized first attempts failed at9505ns before source delivery,
native command submission, FFT processing or pilot output. The separate175MHz
diagnostic replay also failed, as required by its unchanged assertion. **None
of these three attempts qualifies the expired-command negative epoch.**

| Attempt | Original handle | Terminal UTC | Result |
| --- | --- | --- | --- |
| `bank-native-expired-175-v1` | 60089 | 2026-09-10 05:55:08 | exit1, FAIL |
| `bank-native-expired-200-v1` | 85394 | 2026-09-10 05:55:10 | exit1, FAIL |
| `bank-native-expired-175-diagnostic-v2` | 42335 | 2026-09-10 06:04:38 | exit1, diagnostic FAIL |

All original handles were polled to completion by their owning agent. There
was no unapproved retry,200MHz diagnostic, numerical change or product RTL edit.
The first two runs used clean FW`f0f8cbddfbca8bbd4579aa31e6c2ae4519adc64d` /
HDL`3debb55e0f3f125640cb9e8a4e23e4d9d2c09a1b`. The later authorized diagnostic
changed only the test include: two pre-fail displays and their begin/end block.
Its complete predicate, fatal result and all other acceptance gates were
unchanged. Exact source comparison confirms that only the frozen include and
its composed testbench differ from the original115-file inventory.

Runs live under
`hdl/library/starlink_pss_acquisition/build/`, with outer`.vivado.log` and
`.vivado.jou` files adjacent to each named directory. Each contains its original
`frozen_sources`, `scope.txt`, generated FFT wrapper and raw compile/elaborate/
simulation logs. The generated vendor FFT compiled and elaborated successfully;
it had not processed data when the bench stopped.

## Exact failure and diagnosis

All three reported:

```text
PAIRED_REALTIME_PSMA_STOP_FAIL expired request unexpectedly produced work/result/IRQ or control fault cycles=951 canonical=0 scores=0 pilot=0 health=00000000 capture=00000000 ddc=00
Time: 9505 ns
```

The original logs do not identify which disjunct failed. A read-only static-WDB
audit recovered configured0, IRQ0, injection0, strobe0 and zero command/output
counters immediately before failure. Native internal signals were not logged:
their values are`<Blank>`, not0. No live simulation or clocks were used by that
audit. It cannot identify the original internal failing operand by itself.

The separately authorized diagnostic then observed all19 operands at the
unchanged failure. **Correlator busy was1; all other18 operands were0.** Its
sliding-correlator state was1 (`STATE_COEFFICIENT_ENERGY`), configured0,
shadow coefficient count66 and staged generation`15000002`. Active coefficient
valid/generation/energy were still0; commit/accepted/rejected/pending were0 on
this edge. These are observations from the diagnostic, not retroactively added
to the original logs.

This is a test-monitor defect. The actual sliding-correlator RTL defines busy
as state!=IDLE and enters coefficient-energy processing after accepting a
coefficient commit. The same hardware uses non-idle ENERGY, ENERGY_FLUSH,
CHECK, COPY and COPY_FINISH states to prepare/publish coefficients. The original
test incorrectly required busy0 even during that legitimate preparation.
The intended native work/result/counter/IRQ prohibition must remain unconditional;
only the configuration-time interpretation of busy needs correction.

A separate source-initialization caveat remains visible: source_enable=X,
strobe0 during configuration in both original WDBs and the diagnostic. The
compiler warns VRFC10-2938 that source_enable was implicitly declared at the
earlier acquisition-port connection before its later initialized reg declaration.
It is not an operand of the failing native_empty predicate. No known0 source
enable, healthy source epoch or precise compiler initialization mechanism is
claimed. Source-valid gates have not been widened to hide it.

## Preserved contracts, not achieved outcomes

The runners correctly rejected the raw FAIL. Independent read-only invocation
of the negative verifier also rejected all three saved logs. There are zero
submit/reject/register/empty/concurrency/terminal rows, zero native packet rows
and zero pilot bytes. The required62 ordered public reads, actual sample-domain
late branch, exact rejection counters, bounded FFT/pilot witnesses and exact
894 coarse scores/447 map words/2048 pilot bytes were **not reached**.

The unavailable result-port nuance is unchanged: result-store word-valid is
gated by available; an empty public0x54 read can eventually receive the common
AXI adapter's`0xdeaddead` timeout fallback, not a qualified zero packet. The
negative profile continues to avoid0x54/0x58 and require exact empty status,
telemetry and IRQ instead. No expired-request result injection is permitted.
The inherited post-drain late-invalid-map-release and FFT-quiescence gates
remain required; these failed attempts did not reach them.

## Archive and provenance

Archive:`reports/experiments/20260910-bank-native-expired-actual-failure-frozen.tgz`.
SHA256:`a690d6d45308fd19c32093bb601c60bda8f5f949e9065651ad4e392c3f31ab2e`.
Size1510977bytes;387 safe unique regular files, all hash-verified. It retains
all115 frozen inputs per attempt, original scope/IP receipts and generated
wrapper, raw logs/journals, empty pilot files and saved WDBs, plus the final
postrun static-WDB query script/log/journal. Original artifacts were not changed.

The companion`20260910-bank-native-expired-actual-failure-results.json` records
all387 artifact hashes, original115-source inventory and the exact two-file
diagnostic difference. Each complete pre-run115-name/hash inventory still
matches after execution. The two original clock inventories are byte-identical;
all13 frozen Python runtime modules match their pinned FW blobs. All24 cohort
files match the immutable`aa433048…` fixture; event contract`680cdbdd…` and
register words`e17ab5ad…` are unchanged. Generated FFT wrapper SHA remains
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.

The earlier288 offline policy tests and syntax check remain historical offline
evidence, not a functional PASS. These failures demonstrate that distinction.
The proposed correction is test-only, to be separately frozen/offline-tested
and reviewed before new actual175/200 runs. This study makes no runtime,
source30/60, causal acquisition, production-duration, timing, RF or deployment
claim and changes none of the full coarse/native/pilot requirements.
