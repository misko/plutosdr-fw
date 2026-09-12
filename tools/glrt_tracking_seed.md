# Radio-local acquisition seed and bounded worker

`glrt_tracking_seed` connects an accepted GLA1 event to the protected recent-IQ
owner and full timing/CFO resolver. `glrt_tracking_worker` composes that seed
with the existing bootstrap steps and an explicit retention/deadline boundary.
Both currently support the direct **2.5-MS/s upper-edge profile only**.

The caller must attest the radio/profile/reference identities, event sequence
and source continuity. The seed gate preserves the existing Python GLA1 event
contract: only a final accepted decision may enter resolution; candidates and
rejected decisions are ignored. No public wire contract is changed.

## Selection and resolution

Use the retained IQ endpoint to select complete pilots, and the separate
receiver counter to check candidate age. Preserve the existing upper-template
origin convention: acquisition-window origin + reported epoch + 22 samples.
The 22-sample convention is not a newly established universal filter delay and
must not be transferred to 5/15-MS/s filters without qualification.

Select the first four pilots of the most recent 64 complete repeats, reserving
eight samples on each side for timing search. Copy exactly 13,316 CI16 samples
out of the owner. Rational 750-Hz repeat offsets and Q16 seed coordinates use
integer arithmetic even when the original source index is large. Selection
and copy views are retained separately. A concurrent overwrite or expiry
prevents use of the output plan.

The full resolver retains all 17 integer timing hypotheses, each evaluating
four 16,384-point FFTs. The winning integer shift and full-band CFO initialize
the bootstrap candidate. Numerical resolution creates **no accepted tracking
history** and no hardware permission. The original solver, eight supported
history requirement, 200-anchor work budget and 32-repeat forecast limit still
govern future proposals.

The maximum event age at copy is caller-specified and at most one second.
That selection bound is distinct from the worker's source/wall deadlines and
is not a demonstrated live latency guarantee.

## Worker ownership and retention

Allocate one worker workspace outside the capture loop; it is approximately
0.5 MB and should not be a radio thread-stack object. Run it in a background
worker on one accepted event at a time. The capture thread continues publishing
IQ and source snapshots. FFT and moment computation occur outside the IQ mutex.
The caller owns thread creation, event admission, wakeups and cancellation.

The worker requires a CLOCK_MONOTONIC clock, cancellation check, bounded wait
port and synchronous evidence-retention port. It checks cancellation and wall
time before and after each FFT and at bootstrap/retention boundaries. The wall
budget is explicit and at most five seconds; a stopped sample counter cannot
extend it. The wait port must return within 10 ms. Callers must also bound any
retention/I/O callback; an arbitrary blocking callback cannot be preempted by
this synchronous API.

Retain, in order:

1. The source-bound copied seed IQ and original event.
2. All resolver hypotheses and the selected seed.
3. Every past pilot's copied IQ, exact software moments, estimate and source view.
4. The proposed future batch, accepted history and latest checked source view.

These are internal callback tags, not a serialized ABI. Serialize explicit
fields and exact IQ bytes through the caller's evidence writer; do not dump
padded C structures. Failure to retain evidence prevents further handoff.

After the proposal callback, the worker checks cancellation, wall time, source
closure, source deadline and remaining lead again. It can therefore reject a
proposal already present in the journal. Retain the **terminal return status**
and final `checked_source`/`source_checked_ns` before consuming any output.
Only READY permits trying `glrt_tracking_controller_init_handoff`; that
controller independently retains transferred history and rechecks the actual
hardware source counter immediately before SUBMIT. Failed runs invalidate the
live state and clear the output batch while preserving diagnostic fields.

## Qualification and remaining integration

`test_tracking_seed.py` compares integer planning with independent Fraction
arithmetic, event gating with the existing Python decoder, and every resolver
hypothesis with NumPy. It covers large source counters, ring wrap, unavailable
IQ, closure, expiry and failure clearing. `test_tracking_worker.py` runs actual
canonical references, full FFT resolution and C bootstrap arithmetic. It
checks complete evidence ordering, source catch-up, zero-input rejection,
cancellation, wall deadlines, source loss and failures during retention.
Its publication timing is modeled; it does not measure real radio latency.

The ingestion probe does not yet call the worker. Production integration still
needs one bounded pending-event slot, a background thread, wakeups on IQ
publication, explicit seed/past/terminal retention, and clean stop/join before
owner destruction. The controller's hardware submission port remains separate.
Qualify that entire connection under real reception and retain an independent
host GLRT comparison before claiming live automatic tracking.
