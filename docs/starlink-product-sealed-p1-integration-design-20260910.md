# P1-only sealed-product integration design (not implemented)

Base: P1 HDLc144694706b0582668606b6224462c0e8850148d; top
`starlink_pss_fft_bank_owned_product_fence.v` SHA8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c.
Prototype: FW a599e71889da325c0838447bcdf2f41d5ca04cab / HDL
d7b73a9b8012ac7ace5e3c697bd4acdfcdad4cea, independently848PASS. Both exact
DNM remote heads verified after original HDL73873/FW24020 exited0. No inverse
sealed-output, overlap scheduler, arithmetic graft, vendor or top edits here.

## Next bounded change: primitive interfaces first

Extend ADDITIVE variants of the frozen reader/issuer; leave d9c and P1 literal.
No new bank or pipeline cycle is required for these ports:

1. `producer_owned`, existing `reusable`/`reservation`, and the actual exported
   `product_ready` are different concepts. At adapter101/110, qualify private
   take with the ACTUAL exported product_ready net, not a reconstructed
   equivalent. Do NOT merely gate away bank input_valid: retain ungated raw
   product_valid at the d9c observer, qualify input_offer_new for the sampled
   private take, and keep independent issuer observation of closed/unowned and
   X/Z offers (including READY0). Product output retirement uses the same ready.
   Assert private_take equals that exact handshake under forced ready0; test
   missing actual-READY AND missing raw-observer mutants independently. A
   separate admission-capacity port is eligible before producer ownership;
   product_ready is correctly0 then.
2. Export `read_head_valid`, data/position/last/metadata75 and token lease2.
   Head validity is owned/occupied/GOOD/current-clean, independent of core
   enable/READY. It must NOT pop on discovery/preflight. Keep actual core_valid
   separately gated by consumer-start/input-enable. The output metadata is the
   independently raw-checked held descriptor, never an unchecked raw bus.
3. Export `handoff_owned`: existing handoff_seen/published/reader refs plus
   current health, retained through controller receipt consumption and inverse
   admission. `handoff` remains the one actual guard-ACK transfer pulse. Export
   immutable reservation lease/descriptor separately for admission binding.
   Handoff-owned is not producer reuse and clears only on actual lease release.
4. Export narrow write-verdict/current reader-validation/issuer-current evidence
   and all detailed reason banks. No current full75 comparator is added. Keep
   the release-request check OUT of reader validation_fault_now (feedback).

Primitive tests precede top integration: readiness0 on final/interior offered
   product; checked head present while core_enable0; stable head through stalls;
   ACK pulse followed by persistent receipt; missing receipt/phase/head/lease
   qualification mutants; repeated/late ACK; fresh verdict on ACK/release;
   no read/pop on discovery. Re-run the complete848 suite/inverses and continuous
   graph, with all previous failures kept. Metadata75 bit74 and product70 bit69
   remain required. The canonical d9c source does not change.

## Exact P1 wiring/state obligations for later top variant

P1 line194 ARM/job_ready and result_guard169 require destination readiness
before job_accept. Therefore `destination_reserved`/pre-admission capacity uses
`reusable`, not product_ready. After actual forward job_accept, the producer
reference owns the bank and active return retirement uses `kernel_ready &&
product_ready`. Joiner308 keeps the SAME product_ready gate. Inactive admission
capacity must never permit a joiner take: there is no active return then.
Retain the old invariant join input_accept == checked forward guard retirement.

Capture producer admission on `job_accept && !next_inverse`, descriptor from
engine_metadata. Capture completion independently on the EXACT old event at
P1 line480: `return_commit_valid && result_destination_ready && !next_inverse`.
Do not use raw-private final, result_commit's later pulse, or bank publication.
Expected product metadata from477 remains an independent preflight witness;
only the qualified completion authorizes the producer certificate.

While forward_committed, raw prefetched reservation readiness may drive the
guard's ACK destination. Actual adapter handoff must coincide with the guard's
original ACK-clear event (result_guard363): awaiting_ack && mailbox_ready &&
!protocol_fault && !idle_fault_now. Prefer an additive exact ACK-event output,
with every old guard output/state expression literal; alternatively duplicate
that expression only with proved forward_committed⇒inactive and result_busy⇒
awaiting_ack. Never use merely !result_fault. After the pulse, P1 completion_accept
at376 waits !result_busy and consumes persistent health-qualified handoff_owned,
not the now-low handoff pulse. Preserve the post-ACK orphan-before-drain veto.

Inverse discovery/preflight (P1 selected/preflight tuple135/155) sees the checked
HEAD, not reader.core_valid (which is0 until RUN). Bind all70 header/start/exp
bits against independent expected_product_metadata and bind the head token's
two-bit lease to the forward-admitted reservation lease, before issuing the
inverse admission certificate. Keep full existing preflight comparisons. Add
an explicit held product lease2; the old one-bit consume-generation is NOT the
new physical lease and cannot substitute for it. Head must remain position0,
last0, GOOD, same descriptor and same lease through VERIFY/ARM/start.

The checked-input seam is explicit, not a global CHECK_INPUT_BLOCK_IDENTITY(0).
A default-old additive guard variant may use registered product-job binding
plus per-token GOOD/lease/ordinal/TLAST only for an admitted inverse product
job. Source/forward jobs retain full70 equality. If binding is absent, stale,
wrong-phase or wrong-lease, admission/start/core-valid must fail closed. Full
all75 raw offered-word comparisons (including READY0 observations) remain in
the reader, and every accepted token carries its own verdict. Canonical input
guard stays unchanged; its new variant needs a whole-body default inverse and
independent old guard on all source jobs. No mode bit alone grants trust.

Adapter inverse_job_start is the emitted P1 input_job_start in the admitted
inverse phase, not an early job_accept. Pop requires actual certified core
acceptance; compare adapter core_take with that event every edge. Consumer
completion comes from the real input guard. Final prefetch ACK never toggles
lease reuse. Existing product consume-generation, if kept observable, toggles
at actual checked final consumption, not private RAM prefetch.

## Current faults and reset (must be independently proved)

Do NOT feed full P1 input_fault_now/external_fault_now/result_guard.fault_now
back into reader.core_valid: input guard delivery_error depends on core_valid,
so that wiring creates a combinational loop. Preserve the full original input
fault and detailed events on global/result publication and sticky quarantine.
Reader direct vetoes use independent raw/vendor/reset/duplicate/sticky causes
plus its own tagged current verdict. Producer publication is only possible
after qualified forward closure, so source/input framing is then closed;
current duplicate and every retained input fault remain live.

Add an explicit forward-closed raw event fence: while the held forward
completion is live, new core output/status/frame/certified-input events are
illegal, independently of READY. They must directly veto producer publication
and ACK; the original result guard still captures their exact reasons. Do not
OR unqualified core_output_valid/status_valid while normal forward results are
arriving. Do not use result_fault Q alone for a new orphan on publication.
Inverse raw result/status/output mailbox fences remain unchanged. Keep local
staged write/read reasons separately; their two-edge timing is intentionally
not the old raw product-framing ABI. Global summary wiring must not recreate
current full metadata equality or hide any current raw event.

P1 reset synchronizers51–62 do not prove a paused slow source writer actually
observed reset. Proposed fresh common-epoch barrier: asynchronously clear a
slow-domain purge receipt on either external reset, set it only on an actual
slow clock edge that resets the source writer, then synchronize that receipt
to fast. Gate BOTH source reader release and source_fault_fast sampling with
this new epoch acknowledgment, and keep the engine/admission closed meanwhile.
Never gate only product rearm or only data. Hold producer/certificate/reader
purge attestations until all old references are discarded. Test paused slow
clock through either reset assertion/release; no old request/fault toggle may
reopen the new epoch. This is an independent P1-only barrier requirement, not
an implicit import of the other worktree's inverse adapter or CDC proof.

## Integration qualification after primitive review

Create a new additive top with default-old branch, literal restore to8923b42b;
new selector0 must preserve all old RTL, tests, raw CSV and assertions. New
selector1 initially requires the reviewed R/D/S/C/K/M/P1111111 configuration.
Only product adapter/reader, explicit input guard seam and fresh epoch barrier
change; source/output banks, actual FFT, joiner/ROM, arithmetic and scheduling
order remain P1. No source-union. New top current graph and ownership invariants
must pass before asking to prepare an actual vendor run.

Retain original P1 vectors and tests literally as historical/default evidence.
Selector1 needs an explicit accepted-event/latency observer, NOT a claim of
unchanged raw-cycle CSV: the old trace includes cycle/state (TB350/538). Preserve
every numerical expected value and fault/publication condition; annotate only
reviewed timing/ownership/force-target adaptations. In particular preserve
missing status + held-final ready0 (TB567–586), nonfinal ready loss617–622,
late forward faults587–610, active input gaps, inverse final/slow-ACK faults,
post-ACK orphan, and all raw preflight/active metadata corruptions. Product read
fault injectors target actual raw bank→checker tuple; they must not force only
canonical discovery wires and pretend the raw checker was exercised.

Measure using the ACTUAL controller: forward admission/final retirement,
product final take/seal/publication/head/ACK pulse/controller receipt,
inverse admission/config/first/last certified core input, lease release,
inverse final/publication/actual slow ACK, and next forward admission. Prove
one input per demanded core edge after start, including first READY appearing
late and stalls/refills. Prototype3/10/2/1-clock boundaries and1555 actor clocks
are not a receiver pair-overhead bound. The old+12 hypothesis stays unproven;
test actual profile0 and bounded-stall deadlines without changing5215 clocks
or the old29.8us service target. ROM metadata CE remains an independent cone.
