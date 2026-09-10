# Retained-consumer RTL: bounded design proposal

Design only. No implementation, vendor execution, runtime/profile change or
clock change is authorized by this document. Its numerical scheduling premise
is the separately tested `db4945dd4` ledger, not new RTL evidence. Start from the
accepted R1/B1/O1/L1 175 MHz standalone composition; do not silently union P1,
K/M, C1 or the inverse owner's sealed-bank candidate.

## Recommendation: two guard contexts first, one FFT

For the first bounded RTL proof, retain **two instances of the same result-guard
body**, one forward and one inverse, and keep the three original payload banks.
The inverse guard may remain in its real `awaiting_ack` state while the forward
guard owns the same physical FFT's next transform. Add an explicit scheduler
transfer receipt and core-event cutover checker. This costs more control state
than a lightweight parked record but avoids rewriting the protected guard's
ACK wait, descriptor retention, active watchdog, status and final-fence rules.
It does not remove the cutover obligation: both guards see the same untagged
physical FFT, so event ownership must be proved, not inferred from bus routing.

| Option | Preserved old reader obligation | Principal new proof | Estimated declaration cost |
|---|---|---|---|
| Two exact guard contexts | Original inverse guard waits for the real ACK | Correct event routing/cutover and independently retained ownership | One extra 180-bit guard plus roughly 16–24 owner/cutover bits, plus fresh-epoch CDC barrier if not already supplied |
| Lightweight transfer | New parked consumer record replaces inverse guard ACK wait | All the above, plus equivalence of transferred descriptor, sticky health, orphan surveillance and ACK semantics | Illustrative 96-bit record; possibly less if existing bank metadata is safely exposed, not a mapped result |

The guard count is concrete for WATCHDOG=8192: descriptor 70, input/output
counts 20, four observation flags 4, two exponents 10, age 13, return slot 52,
active/awaiting-ACK 2, commit pulse 1, reasons 8 = **180 bits**. No extra FFT,
DSP or 512-word RAM is implied. Duplicate combinational check logic and routing
still cost LUTs and can affect timing; no mapped area or closure claim is made.
The extra 16–24 bits are a planning allocation, not a synthesized bound.

## Source-specific additive modules

The source baseline is the accepted actual run's `frozen_sources` directory:

- `starlink_pss_fft_bank_owned_local_admission_probe.v`, SHA
  `0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235`.
- `starlink_pss_realtime_result_guard.v`, SHA
  `09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2`.
- `starlink_pss_block_mailbox.v`, SHA
  `e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55`.
- The original L1 input guard and arithmetic/IP/goldens remain unchanged.

Proposed new files, not changes to those frozen originals:

1. `starlink_pss_result_guard_owner_view.v`: literal guard body with only module
   rename and read-only outputs for `active`, `awaiting_ack`, exact `fault_now`
   and exact accepted ACK predicate. Require a strict whole-source inverse to
   the SHA above, plus unconditional sampled original/variant equivalence.
   No new state, latency or arithmetic in this observation adapter.
2. `starlink_pss_retained_output_owner.v`: an independently resettable *common
   epoch* owner. Inputs are actual inverse admission, actual final publication,
   observed bank occupied/real ACK, inverse guard ACK acceptance, current/sticky
   faults and fresh-epoch readiness. Outputs distinguish transfer receipt,
   retained reservation, actual reader release and reusable output capacity.
3. `starlink_pss_core_job_cutover.v`: explicit core-owner, reset/quiet/config
   qualification and current orphan/unknown-control reasons. It never resets
   the retained owner or either guard's common-epoch sticky reasons.
4. `starlink_pss_fft_bank_owned_retained_output_probe.v`: additive top with
   `ENABLE_RETAINED_OUTPUT=0` by default. The disabled branch instantiates the
   unchanged original L1 top. The opt-in branch contains the same three banks,
   one input guard, one FFT, unchanged join/product arithmetic, two owner-view
   guards and the owner/cutover modules. Reject unknown/non-Boolean selector
   values; qualification is source-specific R1/B1/O1/L1, not arbitrary modes.
5. A source-specific fresh-epoch mailbox barrier, **if not explicitly supplied
   by a separately reviewed composition**, is mandatory for paused-clock reset
   safety. This is an interface/control addition, never a fourth payload bank.

Do not edit or borrow the inverse owner's frozen issuer as though it already
supports this schedule. Its `phase_lost`, `raw_orphan`, shared `guard_busy`
reference predicates and live return-certificate lifetime assume serialization.
Any later sealed-bank combination requires a separately reviewed issuer variant.

## Producer transfer is not reader ACK

At actual inverse admission, bind an exclusive free output-bank generation to
that inverse job. Keep that tag immutable until real reader release or common
reset. Never self-tag arriving payload with today's bank generation.

At inverse qualified final handshake/publication, create a once-only registered
`producer_transfer_receipt`. Its premises are the original complete input,
512 checked raw returns, one matching independent status, final current fault
veto and actual bank publication. A private last-word take or early status is
insufficient. The inverse guard sets its ordinary `awaiting_ack`; it is **not**
given a synthetic ready pulse. The scheduler alone may now stop waiting for
that guard's `busy` and use the transfer receipt to reset/reassign the core.

The owner records that the bank became occupied after publication before any
free/ready level can count as its reader ACK. A generation/tagged ACK interface
is preferable; with the original toggle mailbox, prove that initial READY at
the publication edge cannot be confused with a later synchronized read ACK.
Actual final-read ACK, inverse guard accepted ACK and a clean common epoch clear
the retained reservation once. Only then may a subsequent inverse reserve it.

If old reader ACK coincides with a current new-forward fault, the physical read
cannot be undone and the exact inverse guard may retire its private ACK wait.
Keep the separate retained owner quarantined, do not grant reusable capacity,
and retain common fault reasons until explicit reset. This avoids feeding the
two guards' combinational fault outputs back into each other's fault inputs.
The healthy invariant relates owner-pending to inverse awaiting-ACK; a failed
epoch may deliberately retain owner-pending after the private ACK bit cleared.

Next-F output reservation is the actual product bank, independent of the old
inverse reader. Next-I admission requires *both* owned complete product input
and genuinely reusable output capacity. If the old reader stalls beyond next-F
completion, hold its product bank and wait. There is no capacity for F(N+2)
before that product is consumed, even if source N+2 is already full.

## Raw-event cutover: essential unresolved boundary

The frozen guard currently treats every frame/status/output event while idle
as an orphan (lines 134–150, 167–171), including the entire old ACK interval.
Two contexts must not route next-F data into the old-I guard and falsely call
it an orphan, but turning off the old observer early must not hide a late old
event. The abstract ledger's `producer_closed=True` establishes no such proof.

Proposed explicit ownership phases:

| Interval | Raw bus owner / required behavior |
|---|---|
| Inverse active through final publication | Original inverse guard sees every input/frame/status/output event; current final veto unchanged |
| After publication, before local reset | Old-I closure observer still sees all raw events; any new event is an orphan, and transfer/current publication is vetoed or quarantined |
| Core reset assertion/held/release, before qualified new configuration | Common cutover monitor sees every raw valid/event signal; require known-zero protocol flags and the preserved reset minimum, do not mask a pulse merely because reset is active |
| New private admission but reset/config closure incomplete | New context may be staged; any raw frame/status/output is still a cutover fault, even if the original guard would accept an early first status |
| Qualified new configuration/input | Frame/input events belong to the selected job; status/results cannot become accepted evidence before fresh frame and complete new input; all original per-word/status/final checks remain |
| No admitted current core job, even with an old reader present | Every raw event remains an orphan; no dead interval between observers |

The new status-window restriction is opt-in and must be explicit. The old guard
permits a matching first status immediately after private admission; default
behavior and its tests remain unchanged. The actual 76-job source has status
at the third raw output, so requiring fresh frame and full input does not change
that tested healthy schedule. Do not substitute a fitted absolute 1300-cycle
timer for independent status evidence.

There is a hard assumption to resolve: vendor results/status carry no job tag.
An arbitrarily delayed old, otherwise plausible event cannot be distinguished
from a new event solely by adding a current-phase tag at reception. The reset
interface must guarantee flushing of the old internal transform; its exact
qualified reset and release behavior must be reviewed from the generated core
and then exercised. A finite quiet window alone does not prove an unbounded
vendor-event latency assumption. If that guarantee is unavailable, neither
two guards nor a lightweight parked context makes the eight-cycle handoff safe;
retain serialization or choose a separately justified closure latency.

## Eight-cycle dispatch audit

The ledger assumes transfer at the *qualified publication* n, not the raw last
word or certificate arrival. Its intended timeline is:

- n: publication transfers producer ownership; inverse awaiting-ACK remains.
- n+1: registered result commit moves scheduler toward ACK_DRAIN.
- n+2: independent transfer/completion receipt is sampled.
- n+3: switch to RESET0 and assert local core reset.
- n+4/n+5: preserve the two reset states.
- n+6/n+7: source/free-product discovery and descriptor verification.
- n+8: next-F private admission, if its source and reservation are valid.
- n+9: existing admission receipt releases core and starts the input guard.
- n+10: first released core edge can supply a known-quiet observation.
- n+11: existing configuration handshake may open the new configured context.
- n+13 onward: unchanged first input edge at admission+5.

Thus a post-reset quiet/config firewall can be checked inside already existing
admission-to-input latency, without claiming that private admission itself is
permission for raw status. Missing quiet/reset qualification must block config
and fault within a separately frozen bound, not stretch the schedule silently.
If review requires closure before private admission, or an extra transfer stage,
the <=8 assumption may fail; add the exact cost and rerun only the offline
ledger first. New sealed publication latency is separate and must also be paid.

## Fault, reset, CDC and watchdog ownership

Keep raw transport/vendor faults and detailed registered reasons as common
epoch evidence. Each current producer retains its direct final-publication veto.
Aggregate registered guard/cutover reasons for sticky quarantine. Any use of
current `fault_now` on top-level transfer/release fences must be acyclic: never
connect the aggregate back to the guards' own `external_fault_now` inputs.
Do not assume a phase-excluded combinational cycle is a structural timing cut.

Per-transform core reset must not clear the inverse reader, its descriptor,
generation, pending ACK, common reasons, or either guard's sticky reason bank.
For either raw reset with slow clock paused, asynchronous outer qualification
must close interfaces immediately; actual slow mailbox state is purged only on
real slow edges. Hold forward-source reader admission and inverse reservations
until a fresh slow purge/idle receipt has crossed back. A default zero tag or
an old high idle bit is not freshness. Do not rearm this common barrier on every
per-transform core reset, or the retained reader will be destroyed/deadlocked.

Each exact guard retains its **8192 active-job** watchdog from its own admission.
An inverse that has published and is awaiting slow ACK is inactive, as before;
do not invent an 8192-cycle reader timeout or reset its age from another job.
Keep original whole-bench 1,500,000-fast and `await_results` 25,000-fast anchors.
Any new epoch progress/retained-reader timeout requires a separately declared
contract; it is not part of the frozen 111-test ledger.

## Bounded offline RTL matrix before any vendor request

1. Default-off whole-source inverse and unconditional guard owner-view equality;
   no arithmetic/core/golden changes. Count the exact declared new state.
2. Scripted legal FFT ports: two full jobs with status at actual raw ordinal 2,
   512 checked words each; I(N) published then F(N+1) admitted before old ACK.
   Witness both actual fast input handshakes and actual slow reads, not state
   elapsed time. Every old/new descriptor, ordinal, exponent and payload stays
   bound to its own job. Require real next-I admission only after old ACK.
3. Sweep old read READY and slow-clock phases; hold old reader beyond F completion;
   release ACK during F input, F output, forward final/handoff, and idle WAIT-I.
   Include final prefetch held without final acceptance, duplicate/wrong ACK,
   simultaneous ACK/current fault and source N+2 already full.
4. Preserve RAW_READY_CERTIFIED_ACK original kinds 3/4/5 and 7/8/9/10, inverse
   final/postcommit fault cases and partial-prefix [128,132] case. In the overlap
   variant the prefix fault may occur after next F was legitimately admitted:
   compare that F's complete visible prefix and prohibit further publication,
   not the old serialized `forward_jobs==1` assertion. Keep that exact assertion
   unchanged for the default baseline.
5. Inject frame/status/output/vendor pulses and X/Z valid/control at every cutover
   edge n..n+13, including matching old status just after new private admission,
   reset assertion/release and configuration. No skipped raw sample or erased
   sticky reason. Preserve missing/delayed/mismatched/padded/duplicate/orphan
   status and all eight exact-final-edge veto tests. Explicitly distinguish
   detectable protocol violations from the untagged arbitrary-late-event
   assumption; do not claim a synthetic producer tag solves the latter.
6. Both raw-reset sides while slow clock paused, old reader stalled, source N+1
   full and F current; resume, require fresh purge and exact first new epoch.
   Per-transform reset during healthy old read must retain it. Exercise tag wrap
   with empty references, and reject an old queued certificate/ACK after wrap.
7. Preserve watchdog anchors: missing result/status fails at original active
   deadline; old published reader may outlive that active deadline without a
   newly invented guard timeout. A stopped reader must still fail the actual
   bench's unchanged bounded drain observation.

Only after this source-specific control proof should one separately request
an actual 175 MHz numerical/overlap run. The model's lower-clock arithmetic is
not authorization for a lower clock, retiming, new constraints or physical run.
