# Offered-input fault summary: initial parent checks PASS, qualification open

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
complete new fault/XZ/boundary/mutation suite and source-bound graph are still
in progress. Only after their review can the new candidate advance to actual
FFT replay and source-matched synthesis/routing.

## Evidence and remaining release scope

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `offer-premise-parent.Qo3DFUXN`: abstract bench, bounded runner, successful
  reference and two rejected mutations, full logs and result receipt.
- `retained-summary-smoke-parent.wO6w9uMv`: parent runner,33 source pins
  before/after, six generated benches and complete compile/simulation logs.
- `checked-publication-parent.qZW4cGCP`: independent root Git-object verification
  of all308 prior checked actual/synthesis archive payloads.

Full15MS/s coarse acquisition from15/30/60, native-rate fine search, independent
2.5MS/s IIO, continuous buffering and causal scheduling,120ms visits/300s blind
comparison, board clock/CDC/RX calibration, then `.18` canary and `.17` Ethernet
deployment remain required. No radio/PPU operation, main merge, production
gitlink promotion or timing exception was performed.
