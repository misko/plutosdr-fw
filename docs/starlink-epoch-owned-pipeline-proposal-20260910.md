# Next bounded experiment: epoch-owned private transfer and sealed publication

Historical read-only proposal at FW265a309a1. Subsequently authorized **offline
standalone implementation only** is described in
[the sealed-bank contract](starlink-epoch-sealed-bank-offline-20260910.md).
Its private checks intentionally use delayed tagged fault capture, not the
immediate reason timing originally suggested below. Keep current L1 actual and
negative route evidence unchanged; no D/S/C/K/M union or existing observer changes.

## What the L1 route actually says

The local admission edit changes only the input descriptor/job-start load at
`starlink_pss_realtime_input_guard_local_admission.v:117`; it does not change
the full metadata check at line80, current framing/delivery faults at line91,
or their use by the rest of the island. It can remove one destination's enable
dependency without shortening the remaining cross-module paths. Place-and-route
also changed; the report alone cannot attribute all slack changes to the edit.

Source points below are in this worktree's `hdl/library/starlink_pss_acquisition/`:

| Measured chain | Actual source connection |
| --- | --- |
| Held phase → input metadata → result fault, -1.549 ns | Local top lines108–114 select the guard tuple; input guard lines80–103 validate and form current faults; top lines212–214 includes them in `external_fault_now`; result guard lines155–156 and274–275 OR external/mailbox faults into reason bit0. |
| Output descriptor → output-bank framing → admission, -1.510 ns | Result guard line223 supplies descriptor/exponent; top lines312–317 feeds the inverse bank; mailbox lines122–128 checks full metadata on private writes; top line253 feeds that current error back; result guard lines167–172 gates `job_ready`; top lines160 and400 register `job_accept`. |
| Product metadata → kernel metadata CE, -1.381 ns | Product-bank current framing enters top lines212–214; result forward retirement lines238–248 gates top line269 join input; ROM updates its block tuple on accepted first-bin input. |

The first path is 6.925 ns (1.477 logic / 5.448 route), the second7.127 ns
(1.324 / 5.803). L1 WNS -1.549 is worse than arithmetic L0 -1.341. These are
not simply multiplier/rounding paths. The issue is that a private consumer's
current check repeatedly becomes another module's admission/retirement control.

## Concrete first slice

Build an **additive, fast-clock-only sealed-bank publication controller**, initially
without the vendor core or receiver integration. Use the existing 512×36 private
bank and exact 75-bit inverse-output metadata as the first physical boundary.
Separate three events that the current mailbox combines on a held final write:

1. `private_take`: consume one owned payload token, including the final token,
   based on reserved capacity and registered local ownership only. It is neither
   a commit nor a delivered-result count. Do not repeatedly consume held finals.
2. `checked_seal`: after all512 writes and the explicitly two-stage validation
   pipeline drain, certify ordinal/TLAST/all metadata bits, bank lease, counts
   and local fault history. Hold payload and metadata immutable while sealed.
3. `publish`: change the existing ownership request toggle only when that seal,
   the matching independent transform/status certificate, epoch and lease agree,
   with no registered quarantine and no remaining live current fault.

This is a new controller/contract, **not another use of existing private_valid**.
Current mailbox lines145–147 require final input acceptance and current framing
to coincide with commit; the new controller deliberately permits a later,
separate commit with no payload write. Existing input/public mailbox behavior
remains the default/reference. No new whole payload RAM is needed for this slice.

On a final private take at edge n, the two checking stages retire by n+2. Earliest
publication is n+3, after registered checked/full evidence; later status may
delay it. A write attempt for the closed lease is a same-edge local error and
cannot be accepted or publish. A legal future-lease ready/valid offer stalled by
ownership is not that error; raw extra core output for the closed job remains an
independent orphan fault even when bank input_ready is zero.
A consumer ACK cannot free/reuse the bank until its last
actual read and every local outstanding validation token have retired.

Use a bank-local two-bit lease, not a truncated sample index. No lease reuse or
wrap is allowed while any token, certificate, read or ACK references that bank.
Both resets flush pipeline and lease validity under the existing common-epoch
contract. Full sample identity remains the original64-bit start; direction,
exponents and all70/75 descriptor bits remain independently checked. A lease is
not a replacement for any numerical/metadata comparison.

## Safety cut: what may leave the global combinational cone

While a bank is OPEN or checking, it cannot publish. Its raw metadata errors end
in local sticky evidence/certificates; other modules may speculatively capture
private descriptors, but cannot start a certified job or release that bank.
When SEALED, no unchecked data write is allowed. The earlier wide comparisons
are then registered facts for this exact lease, rather than a new comparison of
every live upstream bus on the publication edge.

The publication fence must still directly reject **new** events that remain
possible: extra/orphan payload or status/frame events, duplicate starts, local
lease/ownership violations, watchdog expiry, reset and current vendor errors.
Held product overflow remains live until its token is retired; do not replace
it with insertion-only `overflow_pulse`. An active upstream stage cannot be
declared irrelevant merely because a prior certificate exists. Either prove it
closed/sealed with no unchecked transfer or retain its current veto. Registering
the old global fault OR and waiting a few clocks is **not sufficient**: a fresh
fault on the eventual publish edge would otherwise leak a block.

Private speculation may continue on a fault edge; a public request toggle,
certified completion, consumer admission or bank release may not. Keep per-cause
sticky detection and event counts in the originating domain, including simultaneous
causes, rather than deduplicating or resetting them at forward/inverse handoff.
The original proposal suggested retaining old immediate local full-check reason
capture. **Superseded after source review:** that would preserve a parallel wide
cone. The implemented offline option captures private framing/metadata/lease
causes after two edges and retains the offending token's offered lease/index.
No publication or reuse may precede complete check drain. Raw current publication
vetoes remain direct. This is not old counter/fault-timing compatibility; a later
explicit integration/ABI adapter is required. Certificate latency is explicit and
global epoch quarantine must survive private core reset and ACK.
After a slow-domain prefix has been accepted, preserve it as provisional and
honor the measured sticky-fault CDC window; no instantaneous cross-clock revocation
or complete healthy block after quarantine may be claimed.

## Standalone budget and checks

One proposed local controller needs no new BRAM/DSP: it reuses the512×36 bank,
75-bit held descriptor and9-bit cursor. A two-stage descriptor-check implementation
can use25 three-bit equality flags,5 group flags, two tag/valid/error bundles
(at most16 bits each), and at most16 seal/lease/drain/ownership bits: **budget
at most80 additional logical FF** before optimization. This was a target, not
permission to omit state. The offline RTL actually declares317 register bits:
222 reused bank/reader bits and95 control/check bits, plus the existing18432-bit
RAM. The95 exceeds that target by15; external issuer/CDC state is additional,
and this is not mapped utilization or the net delta against the old reset logic.
Local output current-veto fan-in and selector fanout must
be reported rather than assumed cheap. Preserve one private take per clock when
capacity is owned; no one-sample-per-clock claim is made for the FFT itself.

First independent tests use actual RAM/mailbox-style reads and independently
generated ordered tokens, not the candidate's checker expressions. Check all512
words/all75 metadata bits; delayed/absent/mismatched status certificate; all-bit
interior/final corruption; wrong lease/direction/exponent; extra token at n+1,
n+2 and the publication edge; missing/duplicated final; simultaneous faults;
full-bank writes; reader stalls; current and late fault during ACK; one-sided
reset and stale-certificate rejection. Mutants must include unchecked early seal,
one-stage-short drain, current-veto removal, lease truncation/reuse, duplicate
final acceptance and loss of sticky causes. Public request/read sequences must
match an independent transaction model; old private state need not be identical.

Only after that contract passes should an additive island use private forward
transfer into join/product and separate forward-bank certification. Whole-bank
reservation must then prove the realtime core cannot be backpressured mid-frame;
under-capacity or unexpected stalls still quarantine. Keep the generated FFT,
18-bit operands/product rounding/exponents and full independent numerical oracle.
Do not remove old safety cases when replacing cycle-sensitive internal shadows
with event-indexed public checks plus explicit pipeline assertions.

For planning, actual L1/175 observed pair interval is4549 clocks, not a guaranteed
continuous-source bound. Two measured1810-clock core admission-to-commit intervals
plus512 slow reads (896 fast clocks at175) already cost4516 clocks;33 clocks remain
in the observed lifecycle for other handoffs/phase alignment. Source bank loading
is real concurrent work, not free:512 slow clocks, held until512 core reads/ACK.
15 MS/s requires447 results every29.8 us, or5215 nominal175 clocks. Budget at most
**24 added fast clocks per pair** for a later fully pipelined island before
re-evaluation:4549+24=4573, leaving642 nominal clocks (3.67 us). This is an
engineering allocation, not an achieved capacity/stall bound; all outer CDC,
input/output drains, fixed8192 watchdog, scoring/energy expiry and bounded stalls
must be measured again. At150, just3620 core clocks+768 slow-read clocks leaves
only82 of4470 before other overhead: no robust150 MHz claim follows.

## Relationship to existing experiments and baseline choice

| Experiment | What it changes | What it does not solve |
| --- | --- | --- |
| D: distributed fast fault |12 local sticky FF instead of1 (+11 logical FF). | Full raw faults still feed result reasons/publication; a Q reduction can become another bottleneck. |
| S: private next-start scratch | Broader private64-bit `+447` update, no extra FF. | Cross-module current-fault/ownership cone. |
| C: per-cause fault CDC |12 independent two-stage synchronizers (+22 vs scalar pair). | Metadata CDC warnings and fast publication/admission cones; C1 route still -1.830. |
| K: ROM word read-ahead | Speculative/retained word and selector, +37 bits at18-bit components. | Block-metadata capture or global ownership protocol. |
| M: ROM metadata read-ahead | Speculative/retained69-bit tuple and selector, +70 bits. | Moves current checking to a selector; no global publication decoupling. |
| L: local first admission | Input descriptor CE only, no added logical state. | Current input faults and inverse-bank fault→admission; route -1.549. |

D/S actual111 and C1 have completed qualified functional tests but failing routes.
K/M first actual23845 failed quota mid-suite and remains incomplete. The parent
subsequently reported successor10102 complete functional qualification and a
separate synthesis audit; those are not source-composed with this experiment.

Use **one explicit source baseline**, the exact current R1/B1/O1/L1 runtime cohort
62da6a39 and its unchanged arithmetic files, for the first additive controller and
future public reference. Keep arithmetic L0 route/evidence as a comparison, not a
silently substituted source. Do not union all flags. Reuse D/C's separately proved
per-cause recurrence/CDC principles if the new controller needs distributed
quarantine, with new source-specific tests; retain scalar export for the first
standalone slice. S/K/M are orthogonal and can remain absent until their physical
benefit and composition are demonstrated. Production promotion should eventually
collapse reviewed changes into canonical modules, not accumulate probe variants.

The original proposal itself authorized no execution. The later standalone
offline approval still authorizes no vendor FFT, integration or synthesis/route.
Continuous canonical15 from source15/30/60, original-rate
native fine search, independent2.5 MS/s pilot and the full scanner/RF/receiver
qualification remain separate requirements.
