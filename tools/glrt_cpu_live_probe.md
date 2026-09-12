# Bounded GLI1 acquisition and native feedback

`glrt_cpu_live_probe.c` composes continuous IIO capture, CPU coarse search,
retained-IQ resolution/catch-up and the existing native controller on the
radio. `scripts/qualify_glrt_cpu_live20.py` deploys the executable temporarily
to the serial-bound `.20`, calibrates its receive clock, retrieves evidence
and verifies the final idle state. This is a bounded qualification executable,
not an installed autonomous service.

| Component | Input sample rate | Work and location |
| --- | --- | --- |
| FPGA DDC and native source counter | 30 or 60 MS/s | Exports 2.5-MS/s GLI1 IQ and its original source coordinates |
| ARM capture thread | 2.5 MS/s | Attests each 16384-sample refill; retains full IQ and a two-second ring |
| ARM coarse search | 2.5-MS/s IQ windows | Two threads evaluate each complete 14000-sample window; proposes one best peak per attempt |
| ARM resolver/catch-up | 2.5-MS/s retained IQ | Four full 3300-sample pilots, 17 timing hypotheses; then supported past pilots every nine frames |
| FPGA scheduled measurements | 30 or 60 MS/s | 39600 or 79200 samples per 1.32-ms pilot, scheduled from supported history |
| ARM native feedback | Native-rate coordinates, 750-Hz pilot cadence | Retains and associates each GLT1 head, updates history and submits finite future descriptors |

The capture limit is 1536 refills: 25165824 complex samples, or 10.0663296
seconds of RF at the exported rate. There are at most six coarse attempts,
a twelve-second worker deadline, three seconds per resolver worker, and at
most 1500 native measurements with a three-second controller deadline.
The executable's 25-second alarm requests cancellation; all IIO calls and
controller cleanup also have finite timeouts. Shutdown joins workers before
destroying their IQ/FFT storage. A failed native recovery leaves unread heads
uncleared for retained recovery.

REBASE occurs only after capture starts. Its returned native counter defines
a conservative new-epoch boundary. Samples whose signal centers precede that
boundary are recorded but excluded from the worker's IQ owner. The journal
retains the capture visit, GLT epoch, native boundary and projected coarse
boundary. Every candidate and past-IQ view uses that explicit binding.

The worker resolves software candidates without synthesizing GLA1 events.
Supported coarse history is converted to the native rate and passed through
`glrt_tracking_controller_init_handoff`; the controller rereads source time
after retaining a descriptor and before SUBMIT. `handoffs` counts runs with
at least one completed descriptor write, not local initialization. It still
does not claim that returned native measurements were supported.

## Tests and physical evidence

`tests/starlink_glrt/test_cpu_live_probe.py` runs the actual pthread/FFTW
worker with an advancing owned sample stream and explicitly simulated GLT1
ports. Synthetic pilots acquire and retire 1500 native measurements at both
rates. Zero signal, cancellation and source loss submit no jobs. Native
rejection, retention failure and stale admission exercise stop/drain and
unread-head preservation. Those generated port results are not RF evidence.

The first physical 30-MS/s run is
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/cpu-live30-v2/`.
It completed the entire capture while all six candidates failed support.
The independent review checks source continuity, epoch binding, every grid
value, all resolver hypotheses, copied IQ and exact integer moments. It found
zero CDC/pacer drops and no native submissions. Initial scan latency was
759.77 ms; subsequent scans took 675.68–685.84 ms. Resolution/catch-up took
610.77–613.63 ms. The maximum returned-buffer gap was 6.699 ms.

The corresponding physical 60-MS/s run is `cpu-live60-v2/` under the same
evidence root. It also completed 25165824 samples with zero CDC/pacer loss,
six unsupported candidates and no native submissions. Scans took
678.24–765.85 ms; resolution/catch-up took 594.07–606.71 ms. Its maximum
refill gap was 6.856 ms. Independent replay again checked all 219978 grid
values, 102 resolver hypotheses, 48 moment sets and exact retained IQ.
The new 60-MS/s deployment receipt is in `deploy60-live-v1/`.

These establish loaded ingestion and rejection behavior at both rates.
A supported physical acquisition-to-native-feedback loop is still required.
The operator accepts `--lo-hz` for separately bounded frequency revisits and
checks RF state again after capture. Autonomous revisit selection,
reacquisition after a native run and longer refinement remain beyond this
single-loop qualification executable.

## Invocation

Build with the normal ARM compiler, pthreads, libiio and FFTW3. Link
`glrt_cpu_live_probe.c`, `glrt_cpu_coarse.c`, `glrt_cpu_seed.c`, the tracking
worker/seed/resolver/IQ-owner/recent-IQ/live-bootstrap/bootstrap/IQ components,
the native trend/schedule/solver/controller/POSIX components, and tracking
schedule/transport plus GLI1 source and capture source.

```sh
python scripts/qualify_glrt_cpu_live20.py \
  --deployment /path/to/exact/current/deployment/receipt.json \
  --rate 30000000 --binary /path/to/glrt-cpu-live-probe \
  --output /path/to/new/evidence/directory
```

The operator requires the existing production capture authority and PPU serial
lock. It never removes another invocation's files or retries an uncertain
remote execution. A timeout leaves its remote directory available for
reconciliation. Reference payloads must match the reviewed bank hashes.
