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
