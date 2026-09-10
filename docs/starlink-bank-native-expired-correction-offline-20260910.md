# Expired native configuration correction: offline gate

The approved test-only correction passes303 offline tests. No corrected
actual175/200MHz simulation has been launched. The two original failures and
the diagnostic-only failure remain preserved under FW`c7c00feda2f51cdb4818109047cd069c9202c700` /
HDL`fbdb1a2ead05de75eb334de54b2d860bf01c2f37`, documented in
`starlink-bank-native-expired-actual-failure-20260910.md`.

## Exact bounded correction

The diagnostic proved that legitimate coefficient preparation asserted
correlator_busy while the original test demanded0. The new separate
configuration guard permits only these actual RTL states before configured:

| State | RTL value | Required busy |
| --- | --- | --- |
| IDLE | 0 | 0 |
| COEFFICIENT_ENERGY | 1 | 1 |
| COEFFICIENT_CHECK | 2 | 1 |
| COEFFICIENT_COPY | 3 | 1 |
| COEFFICIENT_COPY_FINISH | 9 | 1 |
| COEFFICIENT_ENERGY_FLUSH | 10 | 1 |

It uses exact case matching and four-state comparisons. Unknown configuration
flags, unknown/other states, inconsistent or unknown busy values all fail.
Once configured, IDLE/busy0 is required continuously. Before configured,
source_enable and sample_strobe must both be explicitly0. The18 original
non-busy no-work/fault operands remain an unconditional, unchanged disjunction;
there is no configuration exemption for admission, capture, engine, reducer,
result, error counters or IRQ. Coefficient identity still must remain exact
after configuration.

The diagnostic also found source_enable=X before source activity. The original
compiler explicitly warned that its earlier instance-port use implicitly
declared it before the later initialized reg declaration. The negative-profile
adapter now moves that one existing initialized declaration before its first
use. Both removal and insertion require a unique exact literal anchor. The
healthy base bench/helper and original source sequence, cadence, pauses, indices,
timestamps and payload values are unchanged. An inverse transformation test
proves the resulting composition differs only in that declaration's location
and the already-required negative module name. Actual public submission and
sample-domain command handshake now each explicitly require configured===1,
source_enable===1 and sample_strobe===1; X cannot pass these event guards.

No product RTL, FFT/kernel arithmetic, numerical vectors, event oracle,
expired request identity, public counter expectations, late predicate,
bounded concurrency,62-read inventory, coarse/map/pilot expectation,
stop/late-fault or reset-quiescence gate changed. Empty0x54 reads are still
avoided: common AXI timeout fallback is not a qualified native result packet.

## Executed offline tests

Expired-profile suite:59 PASS in2.66s. Combined suite:303 PASS in10.27s:

```text
python -m pytest -q tests/test_starlink_bank_native_expired.py \
  tests/test_starlink_bank_native_true_pss.py \
  tests/test_starlink_bank_native_paired.py \
  tests/test_starlink_paired_realtime_psma_stop_policy.py
```

The new tests execute the exact extracted configuration-guard task in a tiny
Icarus unit harness over4608 combinations: four-state configured/busy/source/
strobe values and all16 state encodings plus X/Z. Actual RTL constant names and
values are checked separately. Eight deliberately permissive mutations fail:
extra sample-processing state, missing preparation-busy check, unknown config,
casez state matching, unknown source, unknown strobe, missing postcommit state
check and missing postcommit busy check. This is test-policy execution, not
native/FFT behavioral evidence. Structural checks retain all18 unconditional
operands and the strict actual-event source/config predicates.

Declaration missing/duplicate anchors are rejected. An inverse/order test and
Icarus compile/elaboration-only check pass. The latter deliberately uses`-i`
for the absent generated FFT and runs no product clocks. A separate Vivado2022.2
`xvlog --relax -prj compile.prj` compile-only invocation also exits0 and has no
source_enable warning. Its six unrelated pre-existing declaration-order warnings
match the original compiler log and are retained, not suppressed. No vendor
elaboration or simulation was launched for this correction. Ruff and git
whitespace checks pass.

The offline source snapshot is
`hdl/library/starlink_pss_acquisition/build/bank-native-expired-correction-offline-v1`.
The real runner's preflight stops deliberately at a stubbed create_project
fence. Its complete115-name/hash inventory matches after all offline work:
13 Python runtime modules,24 unchanged cohort files and all other dependencies.
Compared with the failed original115 inputs, only the checks include, its
generated bench, the negative adapter and its policy test file differ.

## Frozen evidence

Archive:`reports/experiments/20260910-bank-native-expired-correction-offline-frozen.tgz`.
SHA256:`6ff880d76a446e7be15a8af94f40a8cc307fac7e76e28cfb58c9837468023615`.
It contains120 safe unique regular files, all hash-verified:115 frozen inputs,
scope, compiler project/log and both policy XML receipts. The companion
`20260910-bank-native-expired-correction-offline-results.json` records every
artifact hash and the exact four-source difference from the failed originals.

| Corrected frozen input | SHA256 |
| --- | --- |
| Checks include | `ebdc56ee9752704678acd989f0c22b6b7be11a7af2f239e2a7d1d24092249aad` |
| Negative adapter | `d73f126e1609ff616c9e17116d1a8c30f00a3ed8eb0f2b270006a635d5fe4a7f` |
| Policy tests | `49e204ee97137ff913d5b63035ce0baeb59e04d9a36871f27bc866d4edbd663c` |
| Composed bench | `5ed40f87f29a4e1bde34a6f53d887d9d5d0474b2be9ee45bb6bfc309a9cd7105` |

The fixture remains`aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81`;
event contract remains`680cdbdd674809de536a3323f99d74aa803174af650447cd816bd4ec7b6dfef7`.
Original healthy447/520/520-PSS helpers, runtime RTL and previous archives are
unchanged. The corrected source must receive fresh actual175/200 approval;
offline passes cannot establish command rejection, exact concurrent outputs,
physical timing, causal acquisition, source30/60 or deployment readiness.
