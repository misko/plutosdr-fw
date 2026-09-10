# Checked product bank: additive P1 controller integration (offline)

This is an independent alternative in the ROM-prefetch do-not-merge lane.
It is not composed with inverse-sealed output or retained-output scheduling.
No vendor FFT, synthesis, route, radio, receiver build, or promotion is part of
this gate. The canonical P1 and the reviewed 2,752 primitive tests remain intact.

Owner functional results: preserved **3304PASS135.97s** (552 integration plus
unchanged2752), followed by **554PASS57.77s** for the entire integration suite
after adding only two distinct-payload reset rows. There is no claim that a
single3306-case owner process ran on the final test-only addition. No runtime
RTL changed between these two passes.

## Source boundary

The additive top is
`hdl/library/starlink_pss_acquisition/starlink_pss_fft_bank_owned_checked_product.v`,
default `CHECKED_PRODUCT_BANK=0`. Enabled mode requires explicitly selected
P1 R/D/S/C/K/M/P = 1/1/1/1/1/1/1. Invalid values, including literal X/Z, fail
at elaborated simulation startup. The unchanged source and inverse-output
mailboxes, FFT interface, joiner/ROM/product arithmetic, original publication
predicates, detailed guard/epoch reason bodies, and controller ordering remain.

Three observation-only clones add no state or control changes:

- `checked_product_read_observe`: held owned/GOOD head evidence, excluding live
  faults and READY. The existing current token and offered-bus faults remain
  separately observable and actionable.
- `product_sealed_observe`: forwards that evidence and exports persistent
  handoff ownership without its current-health predicate.
- `realtime_result_guard_observe`: exports the literal original ACK-clear
  event `resetn && awaiting_ack && mailbox_input_ready && !protocol_fault &&
  !idle_fault_now`.

The additive checked input guard retains source-job full identity checking,
ordinal/TLAST checking, every original current delivery/duplicate fence and
reason recurrence. A product job additionally needs an independently bound
start, captures its two-bit lease, and consumes only the queue's same-token
registered GOOD/lease evidence. It does not treat a parameter as authority.
Every actual raw offered 75-bit tuple is still checked upstream, including
full-queue stalls, before its payload can receive GOOD. Product metadata is
the explicit `{5'b0, product70}` encoding, not inverse-output metadata packing.

Five strict inverse patches in
`tests/starlink_oracle/checked_product_top_inverse/` restore the entire original
top, input/result guards, reader and issuer bodies to pinned hashes. An
unrelated source edit cannot be hidden by a matching local inverse hunk.
The new default branch contains the original product mailbox instance body;
its hierarchy is explicitly `original_product_bank.product_bank`.

## Controller authority and dependency directions

Forward actual `job_accept` captures an independent controller origin lease
from the reserved bank, not from discovered reader metadata/lease. The original
expected-product descriptor cache remains a separate job-origin witness.
A fresh ARM mismatch can still coincide with harmless private admission:
registered preflight certification is not a current-edge permission. Original
epoch quarantine plus the new bound-start check block later emitted input.

State/GOOD-only ACK capacity feeds the guard's destination readiness. The actual
handoff needs the exact guard ACK-clear event and independently verifies the
held head against the controller expected descriptor, origin lease, position
zero, non-TLAST and the original forward handoff identity. A registered bound
receipt is captured only at that actual edge. It persists through the existing
completion receipt, phase change and inverse VERIFY/ARM sequence. No dequeue
is possible then: the reader requires the later emitted inverse start and RUN
enable. Lease/reference reuse requires actual final core consumption and drain.

The emitted inverse start rechecks the bound receipt, Q-owned handoff, Q-GOOD
head, independent identity/lease, first position/TLAST, phase and engine
descriptor, plus current Q-derived checker evidence. Lost binding is a current
fault and cannot emit start. Reset, lease release or epoch quarantine clears
the receipt/origin; start consumes the receipt. The input guard captures its
lease on that same sampled start before receipt clearing.

The producer's advertised capacity remains distinct from its sampled READY.
The adapter samples exactly the existing force-visible
`product_bank_ready && !fast_fault` arithmetic interface. Private take requires
known VALID, known sampled READY and advertised capacity. Raw VALID remains
ungated, so closed/unknown offers are not erased by a stall.

Independent raw vendor/overflow/source/duplicate and sticky causes remain
current shared fences. Acceptance-derived issuer D0/D1 are diagnostic Q
upstream, not feedback into the acceptance which produced them. The current
input-guard fence and closed-forward raw events use the separately reviewed
publication/sealing-only route. They still reach the original current result
and ACK fences separately, without feeding reader VALID. This is not a delayed
global-fault exemption or a live certificate/raw-VALID gate.

The wide independent held-head comparison at actual ACK and start remains a
real functional dependency. No timing improvement or closure is inferred from
the complete acyclic connectivity proof. A later tagged registered top verdict
would require its own reviewed contract; it is not implemented here.

## Epoch/reset boundary

An actual slow edge after either raw reset must purge the source writer. A
slow-domain purge receipt, then two fast synchronizer stages, opens
`source_epoch_open`. That gate controls BOTH source reader reset-release and
source-fault sampling. Fast release alone cannot attest a paused writer's
freshness. The slow receipt is legitimate on an edge with `!slow_running`:
the actual source writer is synchronously reset on that edge.

The first literal-old-P1 reset comparison failed as expected from the known
gap, but the failures were not discarded: the old reference emitted stale
block 0 while the candidate emitted fresh block 447; a naturally poisoned
old writer left reference result reason01/quarantine while the candidate
completed all512 recovery outputs. Exact diagnostics and original fatal
assertions are retained in the attempt directories below.

The recovery oracle now checks candidate output payload, complete metadata,
ordinal and TLAST independently from the declared actor inputs and kernel
coefficients. A reset-qualified old P1 is only a secondary comparison, with an
explicitly distinct held-reset provider. This does not change candidate raw
resets, inputs, expected contents, current-fault assertions or epoch fences.
The two original old-provider failures are executed negative controls.

The additional full512 fresh fill while fast is paused is NOT guaranteed by
the unchanged source mailbox. The retained fast ACK is synchronously reset:
after the slow writer resets request/ACK-sync to0, two words can enter before
old ACK1 resynchronizes and closes READY. Both raw-reset directions reproduce
`n=2 req=0 ack_sync=11 fast_ack=1 write=2 epoch=0 fault=0`. These rejected
capacity assumptions remain explicit negative tests. A compliant producer
holds word2 and all metadata for eight slow edges, fast rejoins, real READY
reopens, and the full fresh block completes with512 independently verified
tuples. The old reference is held reset in these two recovery rows; it cannot
be the oracle for a source frame it did not accept.

Upstream must retain the remainder under READY backpressure or report a
gap/expiry. A continuous ADC is not backpressurable, so this reset/recovery
test is not uninterrupted capture or service-capacity qualification. The
paused-fast cases start during forward activity with no inverse-output owner;
arbitrary paused-fast reset with old inverse output outstanding is unclaimed.
No source/output mailbox architecture was extended to make the extra
full-bank-fill expectation pass.

The original3304 pass reused the sample pattern across epochs; its data
freshness evidence alone could not distinguish old payload with new metadata.
The additive CASE19 closes that bounded blind spot in both raw-reset directions:
fresh `I=n%23-4107`, `Q=n%17+3064`, rather than old `I=n%23-11`, `Q=n%17-8`.
All512 source words differ. An independent integer calculation establishes
that all512 rounded product outputs also differ, and every complete fresh
output tuple is checked against that new expected file. Prefix word2 remains
stable for eight slow edges before rejoin. This is explicit fresh data
evidence, still not an arbitrary RAM-upset guarantee.

## Offline proof scope

`tb/starlink_pss_fft512_control_actor.v` is explicitly an identity/control actor,
not an FFT/BFP model. It captures512 actual inputs, observes real configuration
and demand, then returns512 ordered tokens/status. The actual controller,
guards, source/output mailboxes, ROM/joiner and fixed-point product execute.
Python independently computes the declared actor's complex product with exact
integer ties-to-even rounding/saturation and supplies512 expected payloads.
This does NOT replace actual-core numerical, CSV, latency or vendor-event gates.

The new test file is `tests/starlink_oracle/test_checked_product_top.py`:

- Four full pairs in enabled and disabled modes; all2048 accepted output tuples
  match the independent arithmetic/tag oracle and original P1.
- Disabled mode additionally checks all194 original runtime fields, including
  invalid payloads, unconditionally at both clock phases after1ps settling.
  There is no status-payload exception in this deterministic actor.
- Every75-bit raw read identity corruption at full-queue stalled word3 and RUN
  words37/511; every70-bit producer corruption at37/511; ordinal/TLAST and
  malformed early-final control. No bad token reaches core or public output.
- Independent held head/lease corruption at actual ACK, VERIFY, ARM, receipt
  capture and emitted start; missing bound receipt and Q-GOOD; X/Z head words.
- Current raw/sticky faults at producer final, seal, publication, actual ACK,
  controller completion acceptance and receipt consumption. Harmless private
  advancement is not incorrectly treated as public success/failure.
- Real exported READY0 at37 quarantines; finite final511 stall resumes to full
  completion. X/Z READY and ungated X/Z VALID while READY0 remain diagnosed.
- One-sided reset during source, forward, product, handoff and inverse-input
  ownership with slow clock paused; naturally retained source poison; fresh
  recovery and original-old-provider negative controls.
- Executed missing binding, READY, purge/reset and publication-only veto
  mutants; complete LS-aware graph and four restored backedge controls;
  whole-source inverses and fail-closed invalid-parameter witnesses.

The complete graph includes both tops and the actor, rejects unknown operations
and unresolved references, and treats procedural state as state boundaries.
It is not a physical timing or arbitrary forced-wire reachability proof.
Raw post-checker corruption of an unrelated exported transport wire is not
silently included in the checked-token trust contract. The exercised raw-bank
corruptions enter the real producer/read checker inputs, not discovery aliases.

## Logical state and measured actor latency

The reviewed sealed producer/reader primitive is760 logical register bits plus
the existing512x36 payload RAM, versus213 bits in the replaced P1 product
mailbox. Observation clones add0. Top additions are purge3, independent origin
lease/valid plus bound receipt4, held lease widening1; input guard mode/lease3.
Net estimate is **+558 logical bits**, no second payload RAM. No mapped area,
power, timing or CDC-closure claim follows. The old consume-generation register
still exists and is not incorrectly counted as a saving or new lease authority.

Healthy measured controller edges for every enabled job:

| Interval | Fast clocks |
| --- | ---: |
| Final product take to checked seal / publication | 2 / 3 |
| Publication to actual bound forward ACK | 10 |
| Actual ACK to emitted inverse start | 9 |
| Emitted inverse start to first core input | 3 |
| First to last of512 inverse inputs | 511 (no holes) |
| Actual final core input to lease release | 1 |

Relative to each job's own forward start, the identity-actor top adds8 clocks
to first/last inverse input versus P1, about45.7ns at175MHz. This revises the
earlier +12 hypothesis for this actor. It is NOT a measured real-FFT service
budget or proof of the29.8us target; actual controller/vendor latency must be
measured by a separately authorized actual run. Existing numerical arithmetic
pipeline stages are unchanged.

## Retained attempt chronology

All paths below are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`.
No previous run/project is overwritten or relabeled.

- `checked-product-top-v1.bu8mYbJr`: two graph-admission failures for unnamed new
  TB wire-array aliases. Scalar TB ports replaced those aliases; frozen parser
  and RTL were untouched. No simulation ran in the failed attempt.
- `checked-product-top-v2.EnWOmL3T`, original97350:2PASS1.11s.
- `checked-product-top-v3.ZeXjHJNx`, original13609:72PASS8.17s.
- `checked-product-top-v4.9sonWUYU`, original90899:441PASS43.58s. Initial latency
  prints had a cross-always monitor counter race; superseded by an independently
  owned edge counter, not used to infer a hardware latency difference.
- `checked-product-top-v5.z6z25jmv`, original36237:2PASS/16FAIL; old-P1 paused
  reset mismatch/poison evidence. `checked-product-reset-diagnostic.7Ntz3RnD`
  retains two exact tuple/state diagnostic failures without expectation edits.
- `checked-product-top-v6.9toF3Tr9`:4FAIL/16ERROR before simulation, rejecting a
  new continuous TB signed comparison operation. Expected-value computation
  moved into its procedural TB oracle; parser/runtime were not relaxed.
- `checked-product-top-v7.D63D1hm1`, original58099:20PASS5.50s/439deselected.
- `checked-product-top-v8.Ml10MEPM`, original64266:26PASS/2FAIL. Icarus rejected
  X/Z command-line defparams but returned compiler0 and kept default1. Invalid
  cases now use literal TB parameters; compile error/implicit-net text is also
  rejected. New top declarations moved ahead of use, without logical change.
- `checked-product-top-v9.bDgUOwrQ`, original83951:28PASS2.32s/459deselected.
- `checked-product-top-v10.uYBOcI8X`, original86251:121PASS12.93s/407deselected.
- `checked-product-top-v11.7IWjZlYX`, original17139:30PASS2.92s/518deselected.
- `checked-product-top-final-v1.sVVWsH5R`, original60433:3300PASS136.88s,
  full548new plus unchanged2752. Sources were held throughout.
- `checked-product-prejoin-v1.ErYGbN1A`, original27962:2PASS/2FAIL, rejected
  full512 capture while fast paused. `checked-product-prejoin-diagnostic.8GMUdjZ4`
  retains exact two-word prefix/request/ACK/cursor failures in both directions.
- `checked-product-prejoin-v2.1ofXzHIy`, original95398:6PASS2.27s/546deselected;
  two healthy, two explicit rejected assumptions, two compliant held-prefix
  rejoin completions. No runtime change from the3300-pass source.
- `checked-product-top-final-v2.blnGVNR0`, original16693:3304PASS135.97s;
  source FW1238e7d542e37c9ce5456842cc346a05edede7f7 /
  HDLccf8b8189d0757a7d467afb9f2ae4a858d7d1ee0, held throughout.
- `checked-product-distinct-reset-v1.ZWeaqwS4`, original18575:554PASS57.77s;
  all552 old integration rows and both new distinct-payload reset rows.
  Only the additive bench/expected-vector test policy changed; all five
  runtime files and original2752 sources stayed byte-identical.

Final runtime SHA256 bindings:

- top `56f341f02623698d23e66a4b46146eaaca29a25de36aad1b3cdfa5f1d56ed062`
- checked input guard `7e0b6e674a8c70898c050571f66513fd06208c9738954385a3d3207d0cc65d37`
- reader observation `222d09935af40ccd742f6df7344ae6c6682edb435b65fd7481877bdd33b2b344`
- issuer observation `386323152dff509f64688a1d3ea6827d6fb668430365180396df7baf94910f15`
- result ACK observation `b052874e6f1e40d5ee1149256fe89a47abdf35cb06f7a9b46c5c4d4615dcc22e`

Reproduction uses the existing repository/history at the frozen FW/HDL pins,
the existing Icarus toolchain, and the following selected files with Python-B,
`PYTHONDONTWRITEBYTECODE=1`, pytest cache disabled and a fresh persistent
`--basetemp`/JUnit/log directory:

```text
tests/starlink_oracle/test_checked_product_top.py
tests/starlink_oracle/test_product_publication_seams.py
tests/starlink_oracle/test_product_sealed_interface.py
tests/starlink_oracle/test_product_sealed_adapter.py
tests/starlink_oracle/test_checked_product_read.py
```

On the final source this combined selection contains3306 cases. It is an
independent reviewer replay recipe, not an invented owner terminal receipt.
Ruff passes for the new test. A `git diff --check` warning on the required
single-space blank context line inside `result.patch` is unified-diff data;
the whole-body inverse passes and that context is not stripped.

No actual or physical launch is authorized by this report. Final source pins,
all raw receipts and retained failures remain review gates before such a run.
