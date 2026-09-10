# Offered-input fault summary: full51 parent checks PASS, physical gate open

The next retained candidate is additive and default-off. It separates the
common fault summary from repeated certificate-derived fault expressions.
Actual input certification, counters, detailed guard faults, state recurrences,
ACK and public-return predicates are not directly replaced. The original
metadata-dependent input fault remains an immediate common veto.

This is not a routed result or a deployment candidate. Its predecessor remains
at -2.697ns worst setup slack. The checked-product alternative is held after
its -8.324ns route; its complete route evidence has now been pushed on its own
DNM branch (FW7cb773af85f2977cb96894a1b839d2de10f3e828,
HDLbe867adb013e0ee89686075471a589f63a62d985).

## Source review and independent abstract premise

Four new source files under `retained_output_summary_candidate` add
`INPUT_OFFER_FAULT_SUMMARY=0` and parallel cutover/local-guard views. A strict
21-anchor inverse restores all four preceding closed-candidate files exactly.
Independent source review also normalized all12 local guard summary expressions
and the parallel cutover predicate against their original expressions.

The offered beat is `guard_valid && transport_ready`; offered completion is
that beat AND `guard_last`. Under original `input_fault_now === 0`, these must
case-equal both original certificates. Per-owner views use the same original
`routed_inverse == OWNER` mask. Unknown input fault explicitly asserts the
enabled summary veto: this is fail-closed tightening, not unrestricted
four-state equivalence. Offers never become delivered-input certificates.

Parent independently checks an abstract combinational overapproximation with
65536 four-state valuations:1852 known-zero fault cases and7408 owner-mask
comparisons PASS. Missing READY and inverted LAST mutants both fail at concrete
known-zero counterexamples. This is an algebra check, not reachable RTL state,
whole-design formal proof, vendor behavior or hardware validation.

Parent subsequently replays the frozen **real input-guard** premise:512 healthy
clocked words and65536 non-sampling four-state probes at first, second, final
and closed-input states. It passes6844 known-zero cases, including30 unknown
offered beats and3392 masked unknown-identity cases, plus27376 owner-mask
comparisons. Three mutations (missing READY, wrong LAST, wrong owner) are
independently rejected. Bench, unchanged input guard and runner pins remain
exact. Bad/XZ probes are not clocked into state; this does not establish the
separate malformed-input/current-ACK composition requirement.

## Parent scripted composition smoke

Root78127 completes exit0: **six cases PASS**, summary0/1 × original stall0/2/5.
All33 source/helper/vector pins remain unchanged before/after. The harness
retains the preceding composition's full arithmetic/output/state shadows and
its original service/ACK checks, adding only summary/premise observations on
both fast-clock edges. Four-file inverse checks run before compilation.

Each case transfers1536 source, forward, product, inverse and reader words.
Enabled and disabled modes report the same fixture-specific behavior:

| Original reader policy | Forward interval | Summary/premise observations |
|---|---:|---:|
| Normal | 3645 fast clocks | 25513 |
| Parked | 4912 fast clocks | 34971 |
| Held final/handoff | 3645 fast clocks | 25513 |

These are separate three-block runs, not a continuous receiver capacity claim.
The held-final fixture includes two ACKs during forward handoff and1838 held
final-prefetch observations. The parked fixture includes1268 full-source
observations behind a full product. This fixture has **zero ACKs during forward
input**, so it cannot establish malformed-input plus old-inverse-ACK protection.
Dedicated boundary tests must cover that condition separately.

The FFT ports in this campaign are scripted; real unchanged arithmetic and
mailboxes are used, but no new actual vendor FFT qualification follows. The
full offline fault/XZ/boundary/mutation suite now passes below. The source-bound
graph remains under review. Only after its review can the new candidate advance
to actual FFT replay and source-matched synthesis/routing.

## Full51 independent gate

Root49606 completes exit0: **51 PASS in6.96s**,50 source/helper/vector pins
unchanged. The exact test/helper hashes are2fdd8ec285ff2898f053fae7cb9094720e1aec45ed601c5dd4e5a0138fe422c3
and e945d76e9d02e6cee2389f35524c031390a4925ceb708585e087e07d3455a84b.
This suite includes the preceding premise/composition case families; counts
must not be added as51+6+4 independent coverage.

Coverage includes strict source inverses/mutations, default/invalid modes,
the65536 real-input probes and three mutants,1015808 forced-state cutover
comparisons (not reachability), literal common-root decomposition, and16452
common-expression valuations including8192 explicit unknown-fault tightenings.
Both modes retain the original guard stimulus's23 healthy/37 rejection/12 reset
cases, all old state/output shadows, and219315 local-summary observations.
Six composition cases preserve2480 declared bits and three payload banks;
these are logical inventories, not mapped resources or physical performance.

Eight additional module-boundary cases clock an old inverse result guard and
retained owner into their real ACK-wait state, then use the real input guard for
a later forward job. Healthy release passes. Wrong ordinal, early/missing LAST,
delivery gap, duplicate start and X/Z metadata reject release/publication on the
current edge and preserve ownership through quarantine. Four direct-fence
mutants are rejected. In X/Z cases the original guard ACK is X, not silently
coerced to0; both owners' known-zero authority rejects release while the new
summary asserts a known-one veto. Bank READY/request/ACK are driven module
interfaces, not a live mailbox read campaign. A separate publication-request
probe is explicitly not simultaneous two-phase single-FFT reachability proof.

The agent's first run had32 passes and two missing-mailbox dependency compile
errors in the new guard test fixture. That failed attempt is retained. Adding
the unchanged mailbox source fixed only the fixture; its second run passes51
in7.05s. Tested commits: FWff84cb93d3e90f84b0c658a7d24622319310387b,
HDL48b82653d6fcc85ac0276ca1e7b159715cdfc59f. Publication/preparation follow
separately; no actual FFT or timing result is implied by these tests.

## Separate write-side counterexample: pulse-only change rejected

A proposed future write-side cut would consume existing registered guard_commit
instead of combinational final_commit to set forward_committed. Root identified
that this also delays the forward READY mux's transition to published-bank
ownership. A dedicated scripted test confirms the violation: baseline passes;
the pulse-only mutant acknowledges at cycle2736 with committed=0,commit_pulse=1,
bank_valid=0,awaiting_ack=1,ready=1. Its first failure is an ACK before actual
product-bank publication. The later final-inventory failure is secondary to
intentional early stopping.

This mutation is not part of the accepted summary candidate. Any future design
must also prove READY-phase and head-fault observation over the whole retained
token lifetime; final-product pipeline latency alone does not make it safe.
No write-side runtime change is authorized or promoted by this counterexample.

## Evidence and remaining release scope

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `offer-premise-parent.Qo3DFUXN`: abstract bench, bounded runner, successful
  reference and two rejected mutations, full logs and result receipt.
- `retained-summary-smoke-parent.wO6w9uMv`: parent runner,33 source pins
  before/after, six generated benches and complete compile/simulation logs.
- `retained-real-premise-parent.xigrZuV8`: frozen real guard/bench/helper
  snapshots, bounded parent replay, reference and three rejected mutation logs.
- `retained-summary-parent.lSiN2UN2`: full51 parent runner,50 source snapshots,
  before/after hashes, complete pytest logs/XML and execution receipt.
- `commit-pulse-ack-parent.xkh8BtdU`: original baseline and rejected pulse-only
  generated mutant, source pins, exact first-failure logs and result receipt.
- `checked-publication-parent.qZW4cGCP`: independent root Git-object verification
  of all308 prior checked actual/synthesis archive payloads; separate
  `route_audit.py` verifies all28 later route payloads at exact commitbe867adb.

Full15MS/s coarse acquisition from15/30/60, native-rate fine search, independent
2.5MS/s IIO, continuous buffering and causal scheduling,120ms visits/300s blind
comparison, board clock/CDC/RX calibration, then `.18` canary and `.17` Ethernet
deployment remain required. No radio/PPU operation, main merge, production
gitlink promotion or timing exception was performed.
