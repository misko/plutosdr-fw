# Actual-preparation binding table (draft, no vendor run)

Source: exact14-module HDL65cff8a983b2fd8489634939c363f2de230fc512.
Old actual bench SHA68aab9352336490972dba7b05b59c9fcd6c3a813f741af8ee4590f25aec7870b,
from the complete65-file P1 inventory7adf2efa… . Row numbers below refer to that
frozen bench, not a reformatted derivative. New topology means old private
observations cannot be represented as an arbitrary reason/latency allowance.

## Fault/ownership bindings

| Old site / intent | Enabled exact target / boundary | Required observation |
| --- | --- | --- |
| 1056 apparent product VALID while forward status missing | Keep `dut.product_bank_valid` force; it is a discovery claim, not queue GOOD or a certificate | No forward completion/inverse job/start; do not manufacture queue ownership |
| 1064,1105, extra held final, actual producer READY | Keep `dut.product_bank_ready`; sampled A is this wire AND !fast_fault | No arithmetic/private take while A0; raw V stays visible; retain interior quarantine versus held final recovery |
| 1089 product overflow,1090 ordinal,1091 start | Keep real producer `product_overflow/product_position/product_start` ports | No seal/publication/ACK after bad token; preserve independent raw overflow current veto |
| 1075ff current/late forward faults;1110ff inverse commit/ACK;1125ff provisional prefix | Keep actual vendor event, status, source/output ports | Same-edge live publication/ACK veto, sticky detailed reason, no complete poisoned block;128..132 provisional-prefix bound unchanged |
| 1154ff forward ACK identity/ordinal/TLAST | Bind the actual pre-ACK capacity edge, not the later `forward_handoff_ack` receipt; force independent exported head or core head position/last | Actual guard ACK must be0 on that edge; origin/descriptor/lease comparison independent from issuer copies |
| 1154ff post-ACK orphan cases7..10 | Use real `product_guard_ack_event`/`actual_handoff` to locate ACK, then original completion capture/consumption edges | Harmless private advancement may occur; no inverse emitted start/publication/reuse; reasons survive core reset |
| 1212 source metadata,1214 lease,1216 admission receipt | Same source/held lease targets; lease is explicitly two bits when enabled | Source framing/metadata causes remain exact; private guard admission is not itself authority |
| 1215 and1277 forward destination-reservation loss | Enabled `dut.product_reservation=0`, NOT `product_bank_ready=0` | Strict destination bit4 (`10`); separate unchanged A-low tests remain |
| 1269 inverse ownership loss | `dut.product_bank_valid=0` at VERIFY/ARM | Strict ownership bit0; no dequeue, actual start or release |
| 1270 inverse head position7 | Keep exported `dut.product_bank_position=7` at VERIFY/ARM (discovery/binding seam, not raw offered read) | Strict framing+binding mask`0a`; not old framing-only`02`, not an arbitrary superset |
| 1273 inverse descriptor mutation | Keep preflight metadata port; add separate full75-bit exported head vs independent expected descriptor corruption | Descriptor bit3; independently bad origin/head must also suppress actual ACK/start |
| 1280 held lease mutation | Use declared two-bit complement/XOR with at least one changed bit, not truncating through old1-bit injection register | Strict lease bit2; controller-origin/head mismatch is a separately exercised binding bit3 cause |
| 1282 age,1272 output reservation, matching status on fault/next edge | Same old age/output/status ports and drive timing | Exact declared preflight/guard reasons; status reserved bits remain live on valid |
| 1384ff inverse RUN identity/ordinal/TLAST | BEFORE GOOD, `dut.checked_product_bank.adapter.reader.raw_metadata/raw_position/raw_last`, qualified by actual raw position37 offered, including READY0 | Same offered token must never reach core; verdict reason must mature at its reviewed tag/latency; not the original post-GOOD current input-guard framing-mask claim |
| 1388ff forward RUN identity/ordinal/TLAST | Original `dut.source_metadata/source_position/source_last` on actual RUN position37 | Original same-edge input events`011` when ready1,`010` when ready0 remain exact |
| New origin/head/receipt loss | `product_head_metadata`, `product_head_lease`, `checked_product_bank.origin_lease`, `bound_receipt`, QGOOD evidence at actualACK/VERIFY/ARM/start | Independent controller authority; stale internally consistent head with same descriptor but wrong lease must fail |
| Both one-sided resets/extra epochs | Same raw resets; separate paused-clock recovery uses independently declared source tuples | Actual slow purge before reopen, no stale start/output/receipt, exact fresh numerical tuple; no512-prejoin-capture guarantee |

Active inverse post-GOOD wire corruption is NOT silently moved and declared
equivalent. The original forced-wire tests remain literal in disabled/history
scope; enabled BEFORE-GOOD cases preserve malformed offered-token safety with a
different detection boundary. Separate post-GOOD binding tests cover ACK/start,
not arbitrary in-flight registered link upsets. This trusted-link limitation is
the one already reported for the frozen runtime, not a new observer exemption.

## Executed seam witnesses

Additive include:
`hdl/library/starlink_pss_acquisition/tb/starlink_pss_checked_product_actual_binding_probe.svh`.
Test/whole-fixture inverse:
`tests/starlink_oracle/test_checked_product_actual_binding_probe.py`.
Original run:10PASS0.55s at persistent
`checked-product-actual-binding-v1.6e7N1hC2`; no original actual expectation edited.

| Probe | Measured preflight cause | Retained negative control |
| --- | --- | --- |
| Forward VERIFY, actual A0/reservation1 | `00` | Requiring old reservation-loss`10` terminates with exact fatal |
| Forward VERIFY, reservation0/A1 | `10` | Positive rebinding control |
| Inverse VERIFY, exported head position7 | `0a` | Requiring old framing-only`02` terminates with exact fatal |
| Forward VERIFY, source position7 | `02` | Unchanged source-side control |

All four rows assert initial healthy real-controller preflight, and no input
start/config/core take at observation. They are source-binding witnesses, not
vendor behavior or a complete quarantine/recovery proof. Original actor bench
restores byte-for-byte; missing probe/original assertions fail the inverse.

## Observer body disposition

The disabled control keeps the whole old bench, its internal dec20 reference,
all217/qualified216 comparisons, diagnostics, old sampled-final observer and
all original stimulus/assertions. Only DUT module/explicit disabled parameter
and the candidate's product mailbox hierarchy need mechanical mapping.
There are exactly144 candidate mailbox references in the bench and19 in its
P1 binding include; `exact_reference.dut.product_bank` must NOT be rewritten.
Whole-file inverse must recover SHA68aab935… and original binding SHA4b04032b… .

Enabled replacement list, each requiring an exact stored old-body inverse:

- Whole independent raw217 compare/status diagnostics and old final terminal:
  replace with explicitly changed-latency token/ownership accounting, never a
  weakened raw equality or a replacement expected whole-cycle CSV hash.
- Old mailbox sampled-final observer: replace with actual take/seal/publication/
  raw current fence and completion-certificate lifetime; no fictitious toggle.
- Frozen old input/preflight expressions: preserve source side, independently
  express checked-head/lease binding and precisely listed new cause bits on
  inverse side. Do not compare two aliases of expected_metadata as proof.
- Old reconstructed destination/ACK shadow: replace its *input construction*
  with actual result-guard input ports/capacity, retaining whole old guard
  state/output comparison and independent exact current-safe ACK identity.
- Preserve input-port-fed ROM, arithmetic and forward-retirement shadows,
  all status-data valid checks, scalar CDC recurrence and original numerical
  tasks. Any unavoidable additional observer change is another review seam.

The parent reviewed and accepted the exact00/10/0a/02 rebinding and the following
two additional seams. The entire old bodies and their failing old-interface
controls remain retained; these are not arbitrary equivalence relaxations.

### Retained ownership after preflight fault (kind64)

The staged reader's live head VALID falls under quarantine, while its published
reference, reader reference, reader-owned state and lease remain held. Enabled
checks therefore use that retained ownership, unchanged consumption generations,
zero consumed tokens/release/core take/config/start, plus fast fault and
QUARANTINE. Disabled/history retains the original VALID-as-owner assertion and
the executed old assertion failure. The actual observer watches the entire
interval at sampled pre-NBA and both settled fast edges, until common reset.
The final actor witness executes28 retained checks, not only one8-edge endpoint.

### Actual ACK capacity versus scheduler receipt (kind65)

After the guard has really cleared ACK, capacity and its READY input are0 while
the persistent scheduler handoff receipt is1. Enabled old-guard comparison
receives actual guard READY and independently reconstructs the old guard's
reset-qualified ACK-clear event. Separately, the retained receipt must preserve
bound controller origin and owned handoff state before inverse start. The old
READY==receipt assertion remains an executed failure in history/default scope.
Parent independently repeated all14 binding tests and accepted this exact seam.

See `starlink-checked-product-actual-offline-gate-20260910.md` for the frozen93-test
gate, actor-only coverage, whole-source inverses and remaining vendor admission
work. This table and gate authorize no vendor execution.
