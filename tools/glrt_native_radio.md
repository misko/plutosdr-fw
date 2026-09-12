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
