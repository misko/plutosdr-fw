# Software acquisition into retained-IQ tracking

`glrt_cpu_seed` and `glrt_tracking_worker_run_cpu` connect a CPU coarse proposal
to the existing full resolver and causal bootstrap. They do not synthesize a
GLA1 decision. The worker's legacy event/seed storage remains zero, and its
retention callbacks explicitly distinguish `cpu_seed` from the GLA seed.
These are internal C ports; existing persisted GLA1/GLT1 contracts are unchanged.

The proposal contains the original 14000-sample scan-window start, the selected
epoch/frequency/score, and an epoch. All sample coordinates are 2.5-MS/s signal
centers. A live caller must bind that epoch to the active GLT source epoch and
retain its relationship to the independently attested GLI1 capture visit.

The seed selects four pilots from retained IQ at the original measured
candidate epoch. It checks the one-second proposal-age limit,
retention boundaries, source identity, monotonic source/time/generation views,
and exact integer/fractional positioning. Resolution evaluates all 17 timing
hypotheses, with four 16384-point FFTs per hypothesis. Its result initializes
an empty bootstrap history. Only subsequent supported past-pilot measurements
can authorize a future proposal through the existing worker checks.

Selecting a recent nominal repeat before measuring timing rate is unsafe for
a moving signal: at 15 coarse samples/second, a 0.75-second jump shifts the
true pilot by about eleven samples, outside the resolver's eight-sample guard.
Original-epoch resolution leaves propagation to the causal bootstrap, which
updates from supported past observations. This consumes more retained history
and catch-up work, so the existing two-second ring/source deadline and
200-observation budget remain explicit failure boundaries. Overwritten
original IQ is rejected; it is never replaced with an unmeasured extrapolation.
The prior September 12 checkpoints below used the earlier recent-repeat policy.

The same worker now handles both inputs. Cancellation, wall/source deadlines,
retention failures, overwritten IQ, support loss and a late handoff still
invalidate the proposal. Native submission remains a separate responsibility:
convert supported coarse history with `glrt_tracking_trend_from_coarse`, predict
at the selected native rate, and use `glrt_tracking_controller_init_handoff`
with fresh hardware admission checks. This integration does not yet perform
those live steps or install an autonomous receiver.

## Saved-IQ ARM checkpoint

`glrt_cpu_tracking_bench.c` runs a two-thread blind scan, full resolution and
retained-IQ bootstrap on four windows of a previously recorded 2621440-sample
capture. The receiver counter is deliberately **frozen** for this numerical
benchmark. Epoch 1 is an offline replay identity. There is no IIO access or
hardware job submission, and the result cannot qualify live freshness.

The operator `scripts/bench_glrt_coarse20.py --tracking-references FILE` supplies
the complete independently reviewed capture and four direct reference banks.
It uses the normal `.20` ownership and pinned SSH identity, verifies staged
payload hashes, runs the executable with its internal 30-second alarm,
retrieves evidence and removes the temporary files. Firmware/TX/idle state is
attested before and after. No RF collection occurs.

On radio `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`, the
September 12 saved 30-MS/s capture produced scan times of 645.6–652.7 ms and
resolver/bootstrap times of approximately 550–552 ms. All four strongest
proposals failed the unchanged support gate after eight past pilots; no
handoff was authorized. This is evidence of rejection behavior and numerical
throughput, not evidence that the radio or the entire capture lacks a PSS.

The saved 60-MS/s capture was also processed on the same ARM and resident
30-MS/s firmware, with no RF activity. Its four strongest proposals also
failed support. Both captures export the same 2.5-MS/s coarse IQ format.
Evidence lives below
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/` in
`cpu-tracking-arm-v1/` and `cpu-tracking-arm-saved60-v1/`.

Independent replay checks every coarse grid value, all resolver hypotheses and
all exact integer moment words against the original saved IQ. Synthetic
repeated pilots pass the complete blind executable at four window positions;
the zero-signal control yields no candidate. Separate seed/worker tests cover
large source counters, fractional positioning, stale or overwritten IQ,
cancellation, retention failure and handoff expiry, for both worker entries.

## Building and testing

Link the worker with `glrt_cpu_seed.c` as well as its existing GLA seed source.
The saved-IQ benchmark additionally needs `glrt_cpu_coarse.c`, pthreads and
FFTW3. It uses FFTW's estimate plan; its recorded timing excludes plan creation.

```sh
arm-linux-gnueabihf-gcc -std=c99 -O3 -mcpu=cortex-a9 -mfpu=neon \
  -Wall -Wextra -Werror -pthread \
  tools/glrt_cpu_tracking_bench.c tools/glrt_cpu_coarse.c tools/glrt_cpu_seed.c \
  tools/glrt_tracking_worker.c tools/glrt_tracking_seed.c \
  tools/glrt_tracking_resolver.c tools/glrt_tracking_iq_owner.c \
  tools/glrt_tracking_recent_iq.c tools/glrt_tracking_live_bootstrap.c \
  tools/glrt_tracking_bootstrap.c tools/glrt_tracking_iq.c \
  tools/glrt_native_trend.c tools/glrt_native_schedule.c \
  tools/glrt_tracking_schedule.c tools/glrt_native_solver.c \
  -lfftw3 -lm -o glrt-cpu-tracking-bench

python -m pytest -q tests/starlink_glrt/test_cpu_seed.py \
  tests/starlink_glrt/test_tracking_seed.py \
  tests/starlink_glrt/test_tracking_worker.py \
  tests/starlink_glrt/test_tracking_session.py
GLRT_FFTW_PREFIX=/path/to/native/fftw python -m pytest -q \
  tests/starlink_glrt/test_cpu_tracking_bench.py \
  tests/starlink_glrt/test_radio_bootstrap_probe.py
```

The remaining hardware milestone is acquisition during continuous GLI1 DMA,
retained-IQ catch-up while receiver time advances, supported native handoff
and feedback at both 30 and 60 MS/s. Scanner revisit policy and refinement
must follow actual support/loss measurements; these static benchmarks do not
establish them.
