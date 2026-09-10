# P1 sealed-product integration: focused independent audit

Read-only source audit; no RTL edits, test/vendor executions, or physical claim.
The frozen standalone 848-test result is prior evidence, not a test rerun here.
No observed failure of that complete fixture is asserted below. Findings are
specific integration obligations before connecting the new primitives to P1.

## Reviewed source

Read-only tree: `/tmp/starlink-rom-prefetch.j829ht/fw` (HDL nested).
FW `a599e71889da325c0838447bcdf2f41d5ca04cab`; HDL
`d7b73a9b8012ac7ace5e3c697bd4acdfcdad4cea`; original P1
`c144694706b0582668606b6224462c0e8850148d`.

- P1 `starlink_pss_fft_bank_owned_product_fence.v`:
  `8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c`.
- Issuer `starlink_pss_product_sealed_adapter.v`:
  `054cccffabc661a90b2c8a20d63675db4ce64aa271bb09836b207691369f6fbd`.
- Reader `starlink_pss_checked_product_read.v`:
  `30c8cb1dee84c2ebc4289cf101e85572d9655621db6075957557bab445251074`.
- Design as read, `docs/starlink-product-sealed-p1-integration-design-20260910.md`:
  `9299281d218397bfad6524ceffe685fbec25896ab09393a9f4d896f58d65f79d`.

Line references below name files within `hdl/library/starlink_pss_acquisition`.
The design is not an implemented top. Primitive extension authorization does
not establish top/controller qualification.

## 1. Exact ACK and retained scheduler receipt

Result guard line363 clears ACK only on `awaiting_ack && mailbox_input_ready &&
!protocol_fault && !idle_fault_now`. Its `busy` (159) remains true before that
edge. P1 `completion_accept` (376–379) therefore cannot consume that same edge;
its registered `completion_receipt` (471) is consumed still later (502–504).
The issuer's one-shot `handoff` clears `completion_reference` and sets
`handoff_seen` (162). Replacing P1's retained ACK level with that pulse would
lose the scheduler completion witness.

The proposed exact guard ACK output plus persistent, health-qualified
`handoff_owned` is the correct separation. Neither means the product bank is
reusable. Reuse still requires actual certified final core input and drain.

The frozen TB uses `forward_handoff_ready(!guard_fault)`, but also includes
**current** `guard.fault_now` in `current_faults`; hence this audit does not
claim that its complete ACK path lets a current orphan escape. The new top
must prove the exact event after removing broad feedback paths. Minimal tests:

- At the would-be ACK edge, inject each raw output/status/frame/input event
  while `guard_fault` Q is still zero. Guard ACK and issuer handoff must both
  be zero; retain the precise guard reasons.
- After healthy ACK, inject the event at scheduler completion acceptance and
  at subsequent receipt consumption. No new public ACK/reuse/certified job
  admission or unsafe emitted input-start may escape quarantine.
- Hold the receipt through inverse discovery/VERIFY/ARM, checking health and
  the same descriptor/lease. A missing retained-receipt mutant must fail.

Do **not** demand that all private scheduler state stays still on a new fault:
P1 deliberately permits private advancement before registered quarantine
(458–460, 482–504). That is not itself an observable safety failure.

## 2. Two acceptance-derived current-fault backedges

The issuer's `invalid_admission` (62–64) depends on `forward_job_accept`; P1
derives that from `job_valid && job_ready` (197), and guard job-ready (169)
depends on its current idle/external fault. Consequently, feeding issuer bit0
directly back into that current fault creates this structural cycle:

`job_ready -> job_accept -> invalid_admission -> idle_fault_now -> job_ready`.

Similarly, issuer `invalid_completion` (65–67) depends on completion from P1's
`return_commit_valid && result_destination_ready` (480). Routing issuer bit1
into the guard's completed-input fault creates:

`return_commit_valid -> completion -> invalid_completion -> final_public_fault
-> return_commit_valid`.

The frozen fixture avoids these cycles: its guard receives registered
`adapter_fault`, not these combinational issuer bits. Exporting new detailed
current evidence must not automatically OR every bit into every consumer.
Keep immediate local vetoes and separate registered diagnostics for invalid
qualified-handshake requests, or otherwise break/prove the exact dependencies.
This is not permission to delay independent vendor, overflow, duplicate, raw
output/status/frame, or publication-edge fault vetoes. Require the composed
graph to reject both deliberately introduced backedge mutants.

That statement is limited to these two acceptance backedges, not the whole
fixture. During this audit the implementation owner reported that the old
graph helper omitted `LS_` concatenation subnodes. Its corrected read-only
traversal finds a different old-fixture cycle: guard `fault_now` enters TB
`current_faults`, affects handoff-valid/destination-ready, and returns through
guard slot-error. The phase-exclusive mux explains neither an acyclic graph
nor a general proof. Keep the 848 functional simulation result, but supersede
the earlier 3123-node/zero-cycle graph claim with the separately retained
correction. I did not execute that traversal; the actual source expressions
support the reported backedge and the owner is retaining its receipt.

## 3. A certified-input event is not an independent raw reader fence

Input guard lines84,96–97 derive certified input events from core-input-valid.
The proposed forward-closed fence includes those events. Feeding it into the
shared issuer `current_faults` would reconnect:

`reader.core_valid -> input guard certificate -> closed-event fault
-> reader_live -> reader.core_valid`.

Forward/inverse phase exclusivity can make the event unreachable in healthy
operation but does not remove the elaborated cycle. Preserve these events in
the exact global/result-ACK checks. A local publication fence needs an explicit
non-feedback source partition or an independently proved closed-input
predicate. Merely calling a port “producer-only” is insufficient if it still
affects bank output-valid and thus reader combinational checks. Recheck the
whole composed graph, including bank/read current paths. Retain the existing
separate full input-fault reason path without feeding delivery-error back into
reader validity.

## 4. Independent descriptor and lease origin before inverse admission

Issuer132 supplies the reader descriptor from `expected_metadata`, and 135
supplies raw lease from the same held `lease_reference`. The checked head is
good evidence that raw offered metadata matched that owned descriptor, but
comparing two exported copies of these registers is not independent evidence
of the controller job's identity.

Preserve P1's independently captured expected product metadata (477), all70
preflight bits (162–186), and a separate two-bit controller reservation lease
captured at **actual forward admission**. Do not first capture the expected
lease from the discovered inverse head in WAIT_BANK and then compare it with
itself. The old one-bit consume-generation is not the new bank lease.

Minimal controls: repeat an identical start/exponent across two job lifetimes;
offer a stale GOOD ordinal0 head with the old lease; require rejection before
inverse job-accept and kill a missing lease-origin-check mutant. Exercise the
exported head/admission boundary or a locally self-consistent stale actor tuple:
an internal slot-tag mutation may already fail reader head validation and
would not isolate the controller's origin check. Separately
change head descriptor/tag during VERIFY/ARM; require no certified admission
or core pop. Verify position0/last0/GOOD discovery works with core-enable0 and
does not consume data. Two-bit wrap freshness remains conditional on explicit
reference drain/common reset; equality alone cannot reject arbitrary delayed
stale data after wrap.

## Same sampled READY: retain the already identified fix

Issuer101 versus110–111 currently reconstructs the normal private-take
condition. The integration must use the actual exported product READY sampled
by the real multiplier, including forced-low old regression seams. However,
qualifying take must not hide raw closed/unowned/X offers from the independent
observer. Require distinct missing-READY and missing-raw-observer mutants.
The design already states this split; no additional broad redesign is needed.

## Disposition

Proceed with bounded primitive tests and explicit source-specific wiring
proofs. Do not treat port exports or the 848 standalone tests as controller
qualification. No new payload RAM/DSP or cycle/resource measurement was made
by this audit; prior prototype actor timings do not establish a full-pair
service bound. Actual numerical, fault, absolute service, reset/remote-purge,
and physical gates remain separate. Nothing here qualifies the complete
canonical15/native15/30/60/pilot receiver or RF accuracy.
