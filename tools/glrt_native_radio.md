# Finite radio-local native feedback

This experimental C runtime connects GLS1 result association, the full-pilot
moment solver and the causal timing/CFO predictor through local sysfs. It has
component tests and an ARM build. It is not yet deployed as an automatic
tracker, and these tests do not establish physical-signal precision.

The operator must own the PPU lease for the attested Ethernet receiver, preserve
its exact firmware identity and rollback, and retain the initial acquisition.
It must map that acquisition to the native source coordinate and a freshly
rebased GLS1 epoch. Start any coarse IQ buffer before scheduled ownership.
The runtime does not discover a radio, start RX, change RF settings, acquire a
pilot, or rebase the source. A commissioning seed must be labeled as such in
the operator receipt; it is not an acquired pilot.

Build `glrt_native_radio.c`, `glrt_native_posix.c`,
`glrt_native_controller.c`, `glrt_native_trend.c`,
`glrt_native_schedule.c`, `glrt_tracking_schedule.c`, `glrt_tracking_transport.c`
and `glrt_native_solver.c`
together with C99 and `-lm`. The shared trend implementation now also exposes
internal multirate entry points. The default executable mode speaks fixed-60-MS/s
GLS1; `--tracking` explicitly selects GLT1.
The controller's `glrt_tracking_controller_init` entry point accepts explicit
2.5/5/15/30/60-MS/s GLT1 batches and uses `tracking_*` attributes. It checks the
entire bootstrap horizon before I/O, binds snapshots to that rate, associates
heads with the exact prediction/reference phase, and preserves a 100-microsecond
submission lead before and after descriptor retention. Trend observations add
the selected reference-phase delay once. The same finite tick/stop APIs retain
evidence before acknowledgement and cancel uncertain submissions without retry.
The POSIX adapter accepts these additional narrow attributes. Acquisition
handoff remains separate: the executable consumes a retained future prediction.
The Cortex-A9 hard-float static build uses the existing firmware toolchain.
The executable takes five positional arguments:

```
glrt_native_radio ATTESTED_SYSFS_DIRECTORY NEW_JOURNAL BOOTSTRAP_FILE FRAMES SECONDS
```

Append `--tracking` for an explicitly versioned GLT1 seed file. Its content is
the exact `GLT1 VERSION RATE BANK EPOCH TAG START FRACTION PERIOD STEP DELTA
SEED REPEATS EXPIRES` submit text defined in `GLRT_TRACKING_TRANSPORT.md`.
The parser rejects malformed widths, hidden NULs, unknown profiles, overflow
and an expired final pilot before opening the journal or radio directory.
The initial live snapshot must match the parsed rate; a descriptor never
changes the receiver's sample clock. Do not combine `--tracking` with the
legacy `--bootstrap-slices` option. Result summaries include protocol and rate.

Use `starlink_glrt_tracking_journal.review(data, epoch=..., rate=...)` for GLT1
journals. It checks retained ownership before each head, reference phase and
prediction association, finite fit fields, terminal accounting and final clear.
It does not independently recompute the numerical solver. Its `recover` port
requires a confirmed stopped writer and the same attested rate/epoch; it retains
and associates raw heads before acknowledgement, and reconciles an uncertain
POP without repeating it. The GLS1 reviewer/recovery API continues to accept
only GLS1 bodies. Both use the internal length-framed GLRJ1 journal envelope.

Use the canonical `/sys/devices/...` directory supplied by the operator, not
the `/sys/bus/iio/devices/...` symlink. In default GLS1 mode, the seed file contains the exact ten
hexadecimal GLS1 SUBMIT fields (epoch, tag, start, fraction, period, step,
delta, seed, repeats, expires), with no prefixes, signs or hidden terminators.
Bounds are 225,000 total opportunities and 300 seconds, plus at most five
seconds for cancellation/drain. SIGINT and SIGTERM request that same cleanup.
This is a foreground executable; the operator supervises and exports evidence.

The controller keeps at most two owned finite batches. Supported past results
produce subsequent batches of up to 16 repeats, within the predictor's 32-frame
horizon. Global frame ordinals are retained with each descriptor. It retains
every raw head and associated estimate before POP. Descriptors are retained
before SUBMIT, and the source is reread after retention to detect lost lead or
source faults during a slow write. Preemption during the final command remains
subject to the FPGA's explicit late accounting; this is not a hard real-time
guarantee.

Failed or uncertain SUBMIT is never retried. Cancellation drains only associated
and retained heads. Uncertain POP, failed retention or malformed association
ends the process with best-effort cancellation and leaves remaining heads for
the operator. Do not CLEAR those heads merely to restart. A successful end
requires full drain followed by CLEAR and a verified empty, invalidated epoch.
The final JSON result describes runtime completion, not detection or precision.
It includes the largest observed controller step and polling interval; these
are bounded-run observations, not worst-case Linux latency guarantees.

`GLRJ1` is an internal length-framed journal: `GLRJ1\n`, then repeated
`kind length\n` headers followed by exactly `length` payload bytes. Files are
exclusive, mode 0600, and limited to 128 MiB. Each successful retention call
finishes `fdatasync` before returning. On `/tmp` tmpfs this protects against
process failure, not power loss. Export the journal before removal; it is not
automatically deleted. Spool exhaustion fails closed without releasing the
unretained head. The wrapper must budget and verify available RAM before RF.

`starlink_glrt_native_journal.py` independently checks journal framing, retained
descriptor order, exact head/estimate association and drained/final counters.
Its recovery port requires the PPU owner to confirm that the writer has stopped.
It cancels future work, retains and associates each outstanding head, and only
clears after drain. An uncertain POP is reconciled against one counter advance;
it is never blindly retried. A truncated last journal record cannot authorize
an unretained descriptor. Structural review is distinct from numerical replay.

`glrt_native_io_probe.c` uses the same POSIX adapter but never sends a schedule
command. It measures 512 idle snapshots and retained writes, bounded to five
seconds, in a new 1 MiB journal. It requires a cleared idle scheduler. This
probe excludes result reads, POP, SUBMIT, reception load and controller jitter.

Validation: `test_native_controller.py` exercises real C feedback through a
finite fake source/queue and checks retention order, uncertain commands,
source loss, deadlines, acquisition rejection and stale storage timing.
`test_native_posix.py` checks exact I/O, the bounded spool and read-only probe.
`test_native_radio.py` checks strict finite seed parsing and launch rejection.
The nonlinear receive-filter, real 25/2.5 MS/s and live loaded-radio gates remain
separate release requirements.

`glrt_tracking_resolver.c` ports the development bootstrap timing/CFO search
over four saved 3,300-sample pilots. It evaluates 17 integer timing offsets and
68 full-Nyquist 16,384-point FFTs, averaging normalized correlation power and
interpolating each strongest bin. An explicit FFT callback keeps the numerical
component independent of an FFT library, allocation and radio I/O. The caller
owns a 384-KiB workspace and separately attests reference identity, continuity,
source coordinates and causal availability. The result is a software search
estimate; it supplies no detector acceptance or prediction-expiry decision.

The exact search is a numerical/latency reference, not the deployed handoff.
Its `.21` FFTW benchmark reproduces all 238 saved hypotheses across 14 physical
development cases but takes about 562 ms per complete resolution. That exceeds
the sparse-history startup budget before adding moments or I/O. A cheaper
staged resolver or bounded catch-up requires qualification; do not extend
expiry to hide this cost. The standalone controller still consumes an explicit
retained seed and does not call this resolver automatically.

## Bounded catch-up bootstrap component

`glrt_tracking_bootstrap.h/.c` adds an internal 2.5-MS/s seed-to-handoff
controller. It consumes associated software estimates from retained IQ, one
anchor every nine repeats, and catches up while actual source time advances.
After the first eight anchors it uses the existing causal trend and its
unchanged 32-repeat forecast limit. It stops after 200 anchors, rejects
overwritten history, clock regression, association faults and insufficient
support, and emits eight future jobs with an explicit admission lead. The
caller owns IQ retention, source/reference identity, exact moment collection
and final admission-time revalidation. This component does not enable an
automatic CLI handoff or map coarse coordinates to a higher native rate.

The owned `test_tracking_catchup.py` suite passes 46 tests; together with the
existing seed parser/CLI suite, 158 tests pass. An independent Fraction-based
physical replay matches 2,342 past jobs and 1,152 future jobs across all 70
cost/case scenarios. Its independent integer audit checks 1,836 unique moment
records covering all 3,494 occurrences, including every unsupported case.

The bounded saved-IQ ARM benchmark on `.21` includes the full resolver, IQ
copy, exact moments, solve and catch-up control. Three of eight previously
accepted acquisition cases emit fresh handoffs in 710.821–713.488 ms; none of
six controls initialize. One-time FFT planning takes 5.762 ms separately.
Replaying the actual ARM handoffs on subsequent physical IQ yields 73/128,
128/128 and 128/128 supported measurements. The five unsupported acquisition
cases remain visible. These are development results, not a physical accuracy
or every-repeat deployment pass.

Artifacts are `physical-tracking-catchup-v1`,
`tracking-bootstrap-port-replay-v2`, `tracking-bootstrap-benchmark-v1` and
`tracking-arm-handoff-v1` beneath `/srv/bulk/leo/glrt-deployment-20260909`.
The benchmark's source availability follows measured ARM elapsed time, but
uses preloaded sparse IQ fixtures. It excludes live IIO ingestion, recent-IQ
ring ownership, receiver contention and hardware job submission. The radio's
resident firmware and boot identity are unchanged, TX remains disabled, and
temporary benchmark files were removed. No RF was collected.

## Recent IQ and separate live source time

`glrt_tracking_recent_iq.h/.c` supplies caller-owned interleaved CI16 retention.
At 2.5 MS/s, one second uses 10 MB. The ring keeps absolute integer source
coordinates and an explicit epoch, supports partial and oversized delivery
blocks, and distinguishes overwritten data from data not yet delivered. Gaps,
overlaps and source-counter overflow invalidate history until reset. A stale
reader or writer cannot invalidate a newer epoch. Failed reads do not modify
their destination. The capture owner must serialize ingestion and copying;
this component does not create threads or read IIO itself.

The additive `glrt_tracking_bootstrap_live_*` adapter separates the exclusive
retained-IQ endpoint from the actual next receiver sample index. If a hardware
snapshot reports the latest received index, check overflow and add one before
using it as this API's `source_now`. Both coordinates must refer to the same
attested source epoch. A successful past-job request must be copied before
ingestion can overwrite its samples, then associated with `live.core` through
the existing observe port.

Incomplete DMA delivery returns WAIT with no job or measurement. A handoff
searches all eight-repeat batches permitted by the unchanged 32-repeat
forecast bound and compares their start against actual source time plus lead.
The 200-anchor limit still applies. A fixed source deadline bounds advancing
input; the caller must also enforce a wall-time timeout for a stopped source.
Final hardware admission time remains a separate recheck. The legacy
saved-IQ API and the bootstrap state layout are preserved.

The combined ring/live/legacy tests pass 189 cases. The ARM shared-library
build passes with warnings treated as errors; it has not been run on the
radio. Legacy replay v4 matches all 2,342 past and 1,152 future records. Its
initial v3 attempt rejected an old documentation hash; v4 verifies that
noncompiled document against its exact archived/git version, while checking
current compiled sources and unchanged numerical evidence.

`physical-tracking-live-retention-v1` reattests four saved physical captures
and all fourteen development cases. A one-second C ring reproduces every
copied pilot exactly. The three previously initializing cases still hand off
with modeled 4,096/65,536/100,000-sample delivery blocks, at 713.0–730.6 ms
for resolver plus catch-up. An additional queued 65,536-sample block makes
all three reach the 200-anchor limit. All six controls remain rejected.
The independent integer oracle matches 1,584 unique results across 2,703
occurrences. These are modeled delivery/compute scenarios, not measured live
IIO latency. The five other accepted cases still fail startup support.

Follow-up `physical-tracking-live-retention-v2` tests the existing collector's
125,000-sample blocks and a 4,096-sample block with one extra block of lag.
The three cases hand off at 732.6 ms and 717.4 ms respectively; the first
requires thirteen modeled one-ms waits. Future support remains weak in case
1 (74/128 and 73/128), while cases 2 and 3 support 128/128. This does not pass
the physical tracking release gate. The next integration is one radio-local
capture owner feeding retention, acquisition/handoff and independent host IQ
export, followed by loaded ingestion/admission measurement on `.21`.

## Transfer into the finite tracking controller

`glrt_tracking_controller_init_handoff` accepts the qualified bootstrap batch,
its causal trend, the first absolute frame ordinal, and an additional work
budget. It validates the rate/epoch, bounded chronological history, finite
values and remaining forecast horizon. It recomputes the batch from that
history and requires exact descriptor equality before initialization. It copies
the history and retains absolute frame numbering. Invalid input leaves the
controller unchanged; the ordinary initializer still starts with empty history
at frame zero.

Before the first SUBMIT, the controller retains one `tracking_handoff` record
in its internal GLRJ1 journal. The payload is:

```
GLTH1 00010000 RATE EPOCH FIRST LIMIT HISTORY_FIRST LAST_SEEN LAST_SUPPORTED ANCHOR COUNT NEXT
FRAMEOFFSETCFO
...
```

Header numbers are fixed-width lowercase hex: ANCHOR is sixteen digits, all
others eight. LIMIT is the exclusive absolute frame limit. Each observation
line concatenates eight hex digits for its frame, sixteen for the IEEE
binary64 timing-offset bits and sixteen for its CFO bits, followed by newline.
The COUNT observations retain physical ring order, including the NEXT slot.
The maximum 96-point payload fits the existing 4,096-byte record limit.
Implicit initialized/valid/seen state is exactly one; import validation rejects
other values. Source IQ, accepted estimates and acquisition provenance remain
separately retained evidence; serializing the trend does not prove RF truth.

`starlink_glrt_tracking_handoff.decode` independently validates the record.
The GLT1 journal reviewer/recovery path requires this record before permitting
nonzero initial frame ordinals and enforces its finite work and initial
forecast bounds. Missing, late, duplicate or damaged handoffs are rejected.
The GLS1 reviewer rejects this tracking-only extension. GLT1 hardware packets
and submit/snapshot formats are unchanged.

Tests pass 48 handoff cases, 417 controller/trend/journal regressions and 213
bootstrap/CLI cases. They cover 2.5/5/15-MS/s continuation, wrapped history,
large indices/ordinals, lost support, bad state, retention deadlines and
stopped-writer recovery. The first handoff test run crashed because a Python
ctypes callback was replaced after C copied its pointer. Installing the
callback before initialization fixes the test's lifetime error; the corrected
suite passes. The static ARM executable builds with warnings treated as errors
and contains the new handoff/validation symbols; it has not run on-radio.

`physical-controller-handoff-v2` restores only previously consumed history
and drives the actual C controller against a simulated radio port backed by
the retained physical IQ. Three runs begin at frame 604 and each account for
128 results through retain/SUBMIT/read/POP/drain/CLEAR. All 384 moment records
match independent scalar CORDIC/integer calculation, all three journals pass
independent review, and queue high-water is one. Support remains 73/128,
128/128 and 128/128. The other eleven cases retain their missing-handoff result.
The v1 attempt stopped on a summary attribute typo after its first run; v2
changes that field name without altering simulation or numerical gates.

The simulation uses 50-us polling and 100-us descriptor-retention delays.
These are declared model inputs, not measurements of loaded Linux behavior.
This closes the tested controller-history transfer gap. Connecting the live
radio capture owner, measuring admission under receiver load, qualifying the
remaining startup cases, and deployment still remain.

### Passive coarse observer

`glrt_tracking_observer.[ch]` clones a validated 2.5-MS/s coarse history and
measures one retained pilot every nine frames. It keeps an independent history
and has no native-controller, RF-configuration or submission port. The caller
retains the imported history and attests the same four direct reference banks
used by startup. Every new software observation and its exact IQ must be
retained before its history update commits.

One step returns WAIT, MEASURED, DONE or an explicit terminal failure. The
observer allows at most 200 measurements, five seconds of wall time and five
seconds of source look-ahead from its first predicted pilot. It preserves the
eight-support, 96-frame fit and last-supported-plus-32 prediction limits.
Cancellation, deadlines, source loss and retention failure cannot commit a new
history point. Source timestamps are checked against a clock read after the
owner snapshot, since a producer may publish while the observer waits for the
owner lock. As elsewhere, close the owner, join every worker, then destroy it.

This component is passive infrastructure for comparing coarse support with
native loss. It does not feed coarse observations into native feedback, relax
native gates, qualify a new support policy or establish sustained tracking.
`tests/starlink_glrt/test_tracking_observer.py` exercises actual copied IQ,
all four reference phases, large source coordinates, finite loss, retention
transactions, cancellation and concurrent-publication timestamp ordering.

The live CPU probe starts a separate observer thread at native handoff, from
the acquired history's last-seen frame plus nine. Its imported history is the
same attempt/epoch's kind-4 record in `worker.jsonl`. The observer runs at
2.5 MS/s with a 200-measurement, three-second wall/source limit per episode.
It writes `observer.jsonl` and `observer.iq.ci16`; these files never contain
native heads. A start record binds the seed and budgets, each measurement
retains exact IQ, moments and estimates, and a terminal record distinguishes
retained records from committed observations. Cancellation after retention
may leave one final uncommitted record, which must not count as support.

The native controller continues to use only its own native history. After
its terminal recovery, the worker cancels and joins the observer before
declaring itself done. Failed joins prohibit owner destruction or rebase.
Observer history exhaustion and ordinary cancellation remain diagnostic
outcomes; source, deadline, I/O and retention failures fail the qualification
after native recovery. Up to four episodes retain at most 10.56 MB of observer
IQ, within the selected capture's existing 256-MiB evidence allowance. The
operator requires both observer files even for a dwell without acquisition.

### Bounded ARM-local frequency visits

`glrt_tracking_visit.[ch]` and `glrt_cpu_visit_probe.c` add an explicit two-visit
qualification path. The ARM parent accepts two distinct nominal upper-edge IF
centers from channels 1–4 and retains the plan before tuning. It verifies the
serial, native image/rate, ABI, disabled capture buffer, drained and cleared
tracking engine, TX-disabled state and fixed receive settings before each tune.
Only the RX LO changes; existing receive-clock calibration persists.

Each forked child runs the existing 1536-block live probe, bounded to
10.0663296 seconds of 2.5-MS/s IQ and six acquisition attempts. Child evidence
is created exclusively in `visit-0` or `visit-1`. The parent joins the child,
verifies and retains its idle state and source-counter/epoch advance, then
permits the next tune. The total wall limit is 60 seconds, with at most two
additional seconds to terminate and reap an unresponsive child. Total RF is
at most 20.1326592 seconds. A failed child stops the visit loop even when its
cleanup is verified; no generic failure is reclassified as clean tracking loss.

This advances radio-local scanning across frequencies, while leaving sustained
tracking, adaptive revisit order, continuation after qualified native loss and
precision refinement as separate unqualified requirements. It does not select
lower-edge frequencies with the upper-edge reference bank.

At a fresh boot, epoch zero can contain drop counts from calibration before
the first real-refill REBASE. The visit preflight retains those counters and
allows them only in epoch zero with capture disabled and tracking drained,
cleared and fault-free. Every nonzero acquisition epoch still requires zero
CDC/pacer drops. This matches the existing finite probe's baseline-versus-active
epoch distinction; it neither erases a counter nor accepts loss during capture.
### Continuing visits after clean native loss

The two-frequency composition has an internal clean-loss disposition. The
standalone live probe keeps its existing exit semantics. Only the visit child
can return exit 3, and only for a completed and joined worker whose native
controller established acquisition loss, retained/popped every configured head,
drained and cleared the controller, retained all paired IQ, and joined its
observer. Cancellation, retention failures and all final capture/source,
storage-close and cleanup failures prevent that disposition.

The parent maps exit 3 to `GLRT_VISIT_CLEAN_LOSS` and retains result 1 on the
`after_run` transition. It then applies the same idle, fixed-RF, advancing
epoch/counter, retention, cancellation and global-deadline checks used after a
successful capture before tuning again. Unknown exits and signals stop the
sequence. This permits scanning after a qualified loss; it neither changes
native support gates nor establishes sustained lock. Physical qualification
must separately exercise a handoff, clean loss and subsequent frequency visit.

Visit mode explicitly observes worker completion in the full-IQ profile;
standalone full-IQ capture continues to its original finite limit. The first
clean-loss implementation omitted this dispatch and could not emit exit 3 in
the real visit profile. The corrected path has a full-IQ worker-completion
test at both rates. `review_glrt_cpu_visit_loss.py` independently checks the
retained drain/clear, exhausted support horizon and observer join. It must be
combined with final source/IQ, numerical and parent-transition reviews.

### Bounded frequency revisits

The ARM visit executable accepts two, three or four nominal upper-edge LO
centers. Nonadjacent repeats are intentional revisits; adjacent duplicates and
unknown centers are rejected before creating evidence or calling radio ports.
The legacy two-center controller entry point and two-visit wire output remain
compatible. Every plan shares one 60-second wall deadline; it is not reset at
a revisit. Four visits admit at most 100,663,296 coarse samples (40.2653184 s).

Two visits retain full returned IQ. Three/four visits pass `1536-selected` to
each child: six acquisition attempts, 1,536 capture blocks, a 12-second worker
budget and a 25-second child alarm, retaining scan windows, worker windows,
native/observer evidence and source counters. This reduces evidence storage
but does not retain an independent complete IQ stream. The longer selected
profile keeps its existing limits. Native loss in visit mode returns to the
parent after cleanup, instead of initiating an unplanned same-LO REBASE.

Tests cover sweep/revisit ordering at both rates, full-plan preflight, late
deadline/run/retention failure, selected-profile loss ownership and actual
four-child fork/wait/evidence isolation. These are host tests with simulated
radio ports, plus an ARM build. Before physical qualification, the operator
and evidence reviewer must support the selected-IQ multi-visit plan and its
resource budget. No sustained tracking or adaptive frequency ranking is
established by this extension.

### Radio-local scout and sparse follow-up

The opt-in `sparse10-after-scout16` visit plan composes acquisition and the
long sparse profile within one ARM process. It checks two to four upper-edge
LOs with the selected-window, observer-3, scan-64 geometry. Each scout stops
after proving 16 native measurements. The first retained child status that
proves a handoff and completed 16-result run selects its LO; a qualified clean
loss also proves that the scout had acquired a signal. Empty scouts continue
to the next LO, while partial or inconsistent child summaries stop the plan.
If scan64 retains no native handoff but an attempt has normalized single-pilot
power of at least 0.015 and at least six times the mean of the other candidate
scores, that retained activity selects the LO and ends the scout immediately.
This permissive trigger does not claim signal or tracking: the subsequent
scan80/local-2 acquisition and unchanged native gates make that decision. The
two-factor gate separates retained weak events from the measured noise-only
floor while avoiding unused scout attempts after an event.

The parent then retunes to the selected LO and runs exactly one explicit sparse
follow-up child. The ten-second plan uses
`45000-selected-observer9-scan80-local2-track10-sparse10-authority`. The
30- and 100-second plans use distinct `track30-sparse10-authority` and
`track100-sparse10-authority` profiles. They preserve the acquisition
bootstrap's nine-frame cadence, then align the passive authority observer and
2,251 or 7,501 FPGA measurements at ten-frame spacing. This gives the measured
ARM observer 13.33 ms per result instead of 12 ms and removes a growing cadence
mismatch; the earlier stride-nine profiles remain available for
replay of their persisted evidence. A
zero process result is accepted only when the retained status proves one
completed native run with at least 751, 2,251, or 7,501 scheduled measurements.
These represent ten, thirty, or one hundred seconds of 30-MS/s source time at
stride ten and the established sustainable 75-measurement/s cadence. The long child uses the profile's existing bounded
clean-loss reacquisition path (at most three restarts); the short frequency
scouts remain single-visit children. No-signal, exhausted clean-loss,
retention, deadline and child failures remain separate terminal results.
An exhausted reacquisition sequence retains the same explicit clean-loss
disposition after the final joined episode instead of becoming a generic child
failure. The host retrieves the raw evidence archive before decoding the parent
status, so even a new or invalid disposition leaves reviewable diagnostics.

Native and coarse histories advance as independent causal authorities. Each
new valid coarse generation is retained when it advances the previous coarse
generation, even if its final supported frame is slightly behind the latest
native result. Descriptor scheduling still prefers the native predictor. If
stride-ten sampling leaves fewer than eight supported native points in its
96-frame fit window, the retained denser coarse predictor can therefore cover
the next unowned frame instead of ending the episode at that cadence alias.
The established profiles keep the 32-frame descriptor horizon. The new
30- and 100-second stride-ten profiles alone select a 96-frame horizon, equal
to the retained trend's fit window and enough to cross the measured four
rejected nine-frame observer measurements while remaining finite. Their cadence record includes that value, and the independent journal
reviewer applies it with the same per-source monotonic rule over the newest
support from either source.

All scouts share a 60-second controller deadline. The follow-up has its own
320-second deadline, and the complete radio-local process has a 400-second
alarm. With four LOs its finite source-IQ bound is 837,943,296 samples. This
composition removes the host feedback loop from frequency selection and
follow-up launch. Its decision paths and ARM binary are tested offline; a
physical 751-result completion remains a separate qualification result.

### Bounded 30-second continuity qualification

`continuity30-after-scout16` is a separate opt-in plan; it does not alter the
published single-follow-up plans above. It runs at most three scan/segment
rounds. Every round scouts the same two to four reviewed upper-edge LOs and
stops at the first retained activity or native handoff. Its selected follow-up
uses `7500-selected-observer9-scan80-local2-track30-sparse10-authority-segment`.
That child retains the stride-ten, 96-frame-coast, 2,251-result gate, but turns
off same-LO restart so a verified clean loss returns control to the parent for
another frequency scan. Each child gets 7,500 refills, 64 acquisition attempts,
and 49.152 seconds of source IQ, which is sufficient to complete the exact
30-second result horizon.

Segment start and terminal records are appended to `visits.txt`; evidence
numbers remain contiguous across early scout selection, segment loss, and the
next scan. The parent reports scan rounds, segment count, executed visits and
the sample bound under the new `bounded_arm_scout_segmented_followup` scope.
`track_complete` is true only if one segment independently completes all 2,251
results. Separate shorter segments are never added together to satisfy that
gate. With four LOs, the three-round worst case is 670,629,888 samples, or
268.252 seconds at the retained 2.5-MS/s coarse-IQ accounting rate. This is
below the existing single-follow-up plan's 837,943,296-sample bound.
