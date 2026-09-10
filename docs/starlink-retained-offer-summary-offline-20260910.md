# Retained offered-input summary: bounded offline result

The default-off additive candidate passes 51 offline tests; parent independently
repeated all 51. This is not actual FFT, timing closure, continuous input capacity,
native60 integration, causal acquisition or RF qualification. No vendor or radio
tool was invoked in this lane.

## Source and acceptance

Pre-evaluation recipe: FW `b57154502`. Tested source: FW
`ff84cb93d3e90f84b0c658a7d24622319310387b`, HDL
`48b82653d6fcc85ac0276ca1e7b159715cdfc59f`.

The new `retained_output_summary_candidate` directory contains four additive
runtime copies and two test benches. The default `INPUT_OFFER_FAULT_SUMMARY=0`
selects the original common-current expression. Its known-0/1 parameter guard
and wrapper forwarding are explicit. Twenty-one literal inverse anchors restore
all four preceding closed/private candidate files byte-for-byte. No original
runtime, numerical fixture, input guard, FFT, bank, clock or constraint changed.

| New runtime copy | SHA-256 |
| --- | --- |
| Core cutover | c67b62486356215a12cd8e9c2b220c5a877a661bd1b15a13b25f9904171ba330 |
| Wrapper | 7367d534792385eab3b4264f2e36849b18222e6fe848ef7dbc0887394de8bf94 |
| Retained implementation | 3b98a25b8c5d50a18da1692511ae1647c2969fadf5c55d679278b2d5a7bbf0ff |
| Owner guard | 8b853ee26ab18b4639ab0faf156fd75661f86030773c14f5a9843140c52b5d02 |

The offer is `guard_valid && transport_ready`; end is offer AND `guard_last`.
Neither drives real delivery, counters or certificates. Parallel cutover fault
expressions substitute only those two strobes. Parallel owner-local expressions
also tie inherited external fault to zero. The common summary retains the
independent external roots once, rather than propagating that full expression
through both owners again. Original guard state/current/reason/ACK/publication
predicates remain literal; top admission effects through the new common summary
are intentional and separately gated.

The real input guard establishes the key case-equality premise: when its current
fault is known zero, both offered strobes equal both certificates even with
masked unknown inputs. An unknown direct input fault is explicitly tightened to
known-one common fault in the opt-in mode. It is NOT four-state equivalence:
`I || (!I && L)` gives X for I=X/L=1, whereas `I || L` gives 1. Unrestricted old
diagnostic expressions are not changed by that Boolean absorption.

## Executed evidence

- First original handle71358: terminal1, 32 PASS and 2 compile errors. The new
  guard test source list omitted the unchanged block-mailbox dependency. The
  omission was corrected only in that list; all logs and exact first helper/test
  bytes are preserved. This was not an RTL simulation failure.
- Final original1055: terminal0, 51 PASS in 7.05s, at recovery
  `retained-offer-second.RtUsyFvh`. Parent original49606: terminal0, 51 PASS
  in 6.96s, at `retained-summary-parent.lSiN2UN2`; all 50 before/after source
  pins were unchanged. Wall time recorded by the parent owner was 7.116s.
- Real unchanged input guard: all 512 healthy accepted beats, 65,536 non-sampling
  four-state probes at ordinals0/1/511/closed, 6,844 known-zero premises including
  30 unknown offers and 3,392 masked identities, and 27,376 owner-mask checks.
  Missing READY, wrong LAST and wrong owner mutations are rejected. Parent
  independently repeated that bench and all three mutants.
- Cutover: 1,015,808 actual-module combinational comparisons (32,768 binary
  tuples plus single-X/Z perturbations), forced internal state explicitly NOT
  reachable traffic. Common actual top expressions: all 17 independent roots
  plus 16,384 four-state tuples; 8,192 explicit unknown-input tightening cases.
  Missing input/vendor/output roots and weak unknown checking are rejected.
- Original adversarial guard stimulus in both modes: all 23 healthy, 37 rejection
  and 12 reset cases retain full unconditional state/output shadows. Parallel
  local summary decomposition is checked on each sampled edge.
- Eight module-boundary ACK/publication cases clock the old inverse guard into
  real awaiting-ACK state, then use the unchanged input guard for later input.
  Healthy ACK/release works. Wrong ordinal, early/missing LAST, delivery gap,
  duplicate start and X/Z identity preserve immediate quarantine and ownership.
  All four missing/masked/weak direct-fault mutations are rejected.
- Six complete scripted-FFT compositions: summary0/1 × stall0/2/5, unchanged
  arithmetic, source/read identity, full original guard shadows, private-offer
  and closed-input witnesses. Declared state remains 2,480 bits (0 added bits),
  with the same three payload arrays; this excludes modeled FFT state and is
  not a mapped resource count. Parent independently ran the same six profiles.
- Parameter and inverse mutation tests reject invalid/unknown option values,
  missing/duplicated anchors and unrelated source edits.

For the unknown-identity ACK case, the original inverse guard ACK is X, not
silently rewritten to zero. Both unchanged retained-owner boundaries reject it
with known-zero release and matching reasons; the new common summary is known1.
The additional publication request probe is a public-input module boundary,
not a claim that the single FFT can ingest a new F and publish I simultaneously.

Parent abstract premise proof (65,536 overapproximated valuations / 1,852
known-zero cases / 7,408 masks) is separately retained at
`offer-premise-parent.Qo3DFUXN`. It is not substituted for the real-module proof.

## Replay and remaining limits

Use a new non-/tmp recovery directory for TMPDIR, basetemp, log and XML:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH -u PYTHONOPTIMIZE \
  TMPDIR=UNIQUE_RECOVERY /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  -m pytest -q -p no:cacheprovider tests/test_starlink_retained_offer_summary.py \
  --basetemp=UNIQUE_RECOVERY/pytest --junitxml=UNIQUE_RECOVERY/results.xml
```

The fixed collector packages full logs, source snapshots, executed negative
controls, the original failed attempt, and full raw inventories. Only replayable
compiled VVP payloads and symlink aliases are omitted from the portable archive;
originals remain in place. Its receipt accompanies
`artifacts/retained-offer-summary-v1.tar.gz`. Collector execution is packaging
evidence, not an additional member of the 51-test cohort.

Independent typed combinational graph/ancestry analysis is separate evidence:
the FFT reviewer reports PASS for 5,347 continuous nodes / 69 LS, 19 required
roots, 11 excluded echo/certificate predicates and nine rejected source mutants
at `retained-summary-graph-island-v5.cwe7eS6U`. Root review remains separate.
The exact FFT interface is opaque; wire-array element drivers must be traversed
rather than misclassified as payload RAM state. This is elaboration ancestry,
not mapped timing. This candidate removes a serial certificate/reconstructed-fault tail,
not all metadata ancestry: immediate identity fault, handoff/preflight,
unchanged full ACK/return and write-framing/ROM cones remain. The last measured
retained route is still WNS−2.697ns and unqualified. No current candidate timing
result exists. Actual seven-context preparation may follow parent review; all
original numeric/frame/service/reset limits and full references must remain.
