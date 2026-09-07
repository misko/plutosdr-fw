# Stage-15 PSS tracker controller — experimental firmware only

`starlink_pssctl` is the fail-closed userspace boundary for the RX-only FPGA
fine tracker. Each executable is specialized at build time for exactly one
rate and never negotiates geometry at run time: 15 MS/s uses 66 taps, 130
capture samples, and 61 lags (`-30..+30`); 30 MS/s uses 132/260/121; and
60 MS/s uses 264/520/241 (`-120..+120`). The 15 MS/s ABI retains deterministic
sample injection, while the higher-rate ABI deliberately omits it. All three
map only the fixed tracker aperture at `0x79030000`.

Every invocation also requires `--expect-serial`. The value must exactly match
the radio's hardware-derived `/etc/serial` before `/dev/mem` is opened. This is
an extra local guard; PPU still owns host-side USB/interface/route locks and is
the authority for selecting and recovering the radio.

Build and run the native mock/fixture test plus the static ARM target:

```sh
make check
```

`make check` exercises both the original 15 MS/s contract and the 60 MS/s
contract. `make build/starlink_pss60ctl` emits the statically linked ARM
executable used for the 60 MS/s candidate. Buildroot instead compiles the
installed `starlink_pssctl` for the candidate's immutable
`STARLINK_PSS_RATE_MSPS` value.

The test verifies strict ABI rejection, fixture I/Q conversion, coefficient
loading/commit, exact 130-sample injection loading and I/Q conversion, atomic
telemetry, future scheduling, every success-counter delta, retained packet
decoding, fail-with-result-retained behavior, seven-entry batch prequeue/refill,
ordered batch delivery, and accepted-sample clock-slope arithmetic. It does not
access a radio.

The source coefficient memory format is one eight-digit hex `IIIIQQQQ` word
per line. Exactly `66 * rate/15` lines are required. The controller deliberately
converts that fixture convention to the AXI register convention
`{Q[15:0], I[15:0]}`.
Injection fixtures use the same source convention and require exactly 130
lines.

Typical commands on the already PPU-locked, RAM-booted radio are:

```sh
SERIAL=104000bac4950008230026001b440a003a
./starlink_pssctl --expect-serial "$SERIAL" info
./starlink_pssctl --expect-serial "$SERIAL" counters
./starlink_pssctl --expect-serial "$SERIAL" load \
  --coeff upper_minus100k_coefficients_q15.mem --generation 0x07120001
./starlink_pssctl --expect-serial "$SERIAL" clock-slope \
  --duration-ms 1000 --tolerance-ppm 5000
./starlink_pssctl --expect-serial "$SERIAL" track --request 1
./starlink_pssctl --expect-serial "$SERIAL" track-batch \
  --request-base 0x75000000 --count 45000 --period 20000 \
  --lead 1000000 --queue-target 7 --timeout-ms 5000
./starlink_pssctl --expect-serial "$SERIAL" inject-load \
  --samples real_071200_window0_samples_ci16.mem --generation 0x1a120001
./starlink_pssctl --expect-serial "$SERIAL" inject-track --request 2
```

`track` defaults to one million samples of lead (about 66.7 ms at 15 MS/s) and
requires at least 65,536 samples even with `--center` or `--lead`. It snapshots
the sample-clock counters atomically before and after the job, requires exactly
one admitted/completed/published/processed result and zero increments in every
error counter, validates all packet identity/geometry fields, and only then
releases the immutable result bank. On a packet or counter-gate failure it
leaves the result retained for diagnosis and exits nonzero.

`clock-slope` brackets two accepted-sample index snapshots with
`CLOCK_MONOTONIC` reads, uses each host-read midpoint, and compares the measured
slope with the ABI-fixed 15 MHz clock. The default observation is one second
with a 5000 ppm bound. Its JSON records both MMIO read spans so host scheduling
uncertainty remains visible.

`track-batch` uses the existing ABI 1.2 command FIFO; it does not require an RTL
change. The frozen Stage-15 continuity geometry is one center every 20,000
accepted samples (750 Hz), one million samples of initial lead, and all seven
usable FIFO entries. It emits one validated `batch_result` JSON object per line
and a final `batch_summary`. The controller refills after every completion,
preserves result order, records conservative post-submit lead, requires at least
65,536 samples of lead for every accepted command, and verifies aggregate
success-counter deltas plus zero change in every error counter. Saturated counters
or insufficient counter headroom are rejected before the first submission. A
partial failure leaves prior lines as valid NDJSON and exits nonzero without a
success summary.

`inject-load` clears, writes, and commits an immutable 130-sample fixture.
`inject-track` arms that fixture at a future absolute accepted-sample index,
schedules `TRACK_ONE` at `start+32`, and succeeds only if both the ordinary
packet/counter gates and the injection completion/generation gates pass. The
FPGA substitutes I/Q before the shared tracker/RX-DMA fan-out; strobe, enable,
index, and timestamp remain source-derived. A late start, incomplete fixture,
overlapping command, or accepted-index discontinuity is sticky and fail-closed.
This is deterministic hardware-path evidence, not live Starlink evidence.

## Continuous-acquisition library checkpoint

`starlink_pss_acquisition.c` is the ARM policy layer for the separate `PSMA`
phase-map bridge. All supported images expose the same
post-conditioning geometry: 20,000 one-sample phase bins at 15 MS/s, 64
frames per map, 16-bit map words, and two immutable banks. The parser accepts
exactly ABI 1.0/capability `0x1f` and ABI 1.1/capability `0x3f` for the 15 MS/s
path, ABI 1.2/capability `0x7f` for the 30-to-15 MS/s x2 DDC, and ABI
1.4/capability `0xff` for the cascaded 60-to-30-to-15 MS/s x4 DDC with
coherent 64-bit accepted/emitted counters. Unknown versions or mismatched
capability words fail closed. For ABI 1.2/1.3/1.4 the
library additionally requires the exact input rate, stage configuration,
raw-input group delay, coefficient energy, and complete 256-bit Python-oracle
contract hash before acquisition can be enabled. The dedicated
`starlink_pss_acqctl` executable links this layer without changing the older
sparse-tracker CLI. It maps only the integrated acquisition aperture at
`0x79040000`, requires an exact `/etc/serial` match before opening `/dev/mem`,
and is installed only by the experimental DNM Buildroot package.

`starlink_pss_acqctl info` validates and reports the immutable rate-specific
contract. `snapshot` reports one atomic telemetry view. `candidate` owns a
bounded lifecycle: flush/enable, require a clean health epoch, copy and release
exactly three consecutive maps in oldest-generation order, run the fixed
seven-drift search on the ARM, take a final health/DDC observation, and
disable/flush before emitting JSON. Failure and handled interruption also
attempt disable/flush. Its output is deliberately labelled
`candidate_measurement_only`; it has no thresholds and therefore cannot claim
PSS detection or frame lock. A later frozen qualification policy can consume
these measurements through the already-tested lock controller without
silently promoting an exploratory threshold into a detector contract.

`progress --timeout-ms N` is the bounded failure-analysis path. It first
requires a disabled engine, flushes and enables acquisition for one observation
interval, atomically snapshots telemetry on both sides of that interval, and
then disables and flushes the engine. Its JSON reports the AD9361 ADC-valid
counter at `0x790200b8`, acquisition ingress occupancy/drops, score and map
progress, DDC counters, and every existing fault class. The command is
diagnostic only: `pss_detected` and `frame_lock_claim` are always false. This
makes a no-map timeout distinguishable as no ADC strobes, no CDC ingress, a
detector quarantine, or a merely slow map without opening an IIO DMA buffer.

The copy sequence takes one atomic hardware snapshot, reads exactly 20,000
zero-extended words, brackets the copy with a second atomic snapshot, and
releases the selected bank only after its generation, start index, command
status, and all acquisition/bridge fault epochs remain coherent. ABI 1.1 adds
one atomic snapshot of ingress drops/FIFO occupancy, scheduler gaps/index
errors/overflows, detector faults, phase discontinuities, zero denominators,
candidate FIFO occupancy, and sticky cause flags. ABI 1.2/1.3/1.4 also recognize
DDC arithmetic saturation as a continuity fault. Continuity checks reject a
copy when any data-integrity fault epoch changes or saturates; changing queue
occupancy and zero-denominator telemetry remain observable but do not falsely
invalidate an otherwise coherent copy. ABI 1.0 snapshots synthesize zero for
the absent health fields and never access the newer register ranges. ABI 1.1
likewise never reads the ABI 1.2/1.3/1.4 DDC contract range. Failed copies retain
FPGA ownership. Each successful copy carries its before/after health
epochs; `pss_map_copies_contiguous()` accepts only adjacent generations and
1,280,000-sample start-index steps with unchanged, nonsaturated fault counters.

Candidate extraction keeps three consecutive maps and evaluates at most seven
strictly increasing shift-and-sum hypotheses. The production bank is
`[-12, -8, -4, 0, 4, 8, 12]` bins per 64-frame tile: approximately
`[-9.375, -6.25, -3.125, 0, 3.125, 6.25, 9.375]` ppm around the nominal
20,000-sample period. It preserves the Python oracle's tie order (smallest
drift, then smallest phase), exact odd/even median and MAD construction,
peak-to-median ratio, robust z score, and estimated frame period.

The fixed working set is about 320 kB: 120 kB for three maps, 160 kB for two
20,000-word `uint32_t` scratch arrays, and 40 kB for the incoming immutable
copy buffer. The state controller is explicitly
`ACQUIRE -> CONFIRM -> LOCK -> TRACK -> HOLDOVER -> ACQUIRE`. A lock requires
multiple threshold-passing, phase/cadence-consistent observations. Metadata or
hardware-health discontinuity resets acquisition without consuming the current
candidate; bounded misses enter holdover and then return to acquisition.

The native C test covers all four supported ABI contracts, exact x2/x4 DDC
metadata and hash rejection, the extended health-word unpacking, proof that
ABI 1.0 never reads ABI 1.1 registers, the complete
20,000-word transfer, oldest-ready-bank selection, disabled/ambiguous wait
rejection, no-release failure paths, ingress/base fault epochs and
map continuity, mutable non-fault telemetry, fixed-memory drift extraction,
tie and finite/zero-MAD cases, unsafe-bound rejection, and the complete state
path.
`tests/test_starlink_pss_acquisition_c.py` additionally compares C against the
frozen Python acquisition oracle across randomized odd/even map sizes and a
zero-MAD tie. This checkpoint is packaged candidate-selection and policy logic,
not an on-radio result, live PSS detection, or demonstrated frame lock.

## M2 deterministic timing qualifier

`starlink_pss_m2ctl` is a separate, stripped static controller for the
15 MS/s `acquisition-injection` profile. It requires both the exact PSMA v1.1
contract at `0x79040000` and the exact PSSI v1.0 contract at `0x79030000`.
The host supplies the sealed 130-word `IIIIQQQQ` fixture and 20,000-word score
profile; the controller converts the fixture to PSSI's `{Q,I}` register order.

For each requested phase, the controller consumes a baseline map, calculates a
future acquisition-map boundary with 500,000 samples of host scheduling margin,
and arms the fixture so its known score peak lands at that phase. It keeps
copying and releasing every intervening map, compares all 20,000 target words
against `64 * periodic_score[(phase + injection_delta) mod 20000]`, and requires
one unique peak at the requested phase. The default phase set is the zero edge,
wrap edge, and deterministic interior phase `0,19999,7311`.

Every copied map must have adjacent generation/start metadata and completely
zero fault/health telemetry. PSSI must report the same sealed generation and
exactly 130 completed repetitions. On any error or handled signal the tool
disables and flushes PSMA and exits without a success summary. Its NDJSON says
`stimulus=deterministic_internal`, distinguishes the hardware timing result
from live reception, and always keeps SSS and frame-lock claims false.

The native tests independently cover the PSSI ABI/load/arm/completion contract,
edge-phase scheduling, exact 20,000-bin map construction, one-word rejection,
and overflow/geometry failures. `make sanitize` applies ASAN/UBSAN to these
layers. The deployment controller is statically linked and stripped for the
radio's bounded `/tmp`; it is not installed into persistent firmware.

This controller and FPGA belong only on
`codex/starlink-rx-only-do-not-merge`. They must not be merged into HDL or
firmware main. Generic PPU radio-mode support remains separate and mergeable to
PPU main.

## Receipt-bound hardware probe

`scripts/starlink_pss_hardware_probe.py` closes the gap between a passing PPU
RX-only v2 RAM receipt and one bounded acquisition-controller measurement. The
Starlink-specific probe remains on `codex/starlink-rx-only-do-not-merge`; it
imports an exact clean PPU checkout for its serial-scoped radio/route locks,
USB target revalidation, RX-only runtime attestation, and SSH policy. It accepts
only serial `104000bac4950008230026001b440a003a`, runtime target
`ad9363a-1r1t`, and the 15, 30, or 60 MS/s v2 candidate matching the plan.

The workflow has three deliberately separate commands:

1. `plan` is offline. It validates the byte-exact candidate plan, reviewed PPU
   operation plan, and passing/cleaned RAM receipt, then writes a new mode-0600
   probe plan into an owned mode-0700 directory.
2. `execute` requires the plan's exact confirmation phrase. It reacquires PPU's
   locks and `/32` route, reattests the same RX-only candidate, opens only that
   radio's concrete `usb:bus.device.5` IIO context, sets and reads back the PHY
   and capture rates, proves factor-one capture, caps AD9363A RF bandwidth at
   20 MHz, and runs `info`, `snapshot`, `candidate`, `snapshot`, `info`. The
   controller must start and finish disabled and may emit only a
   `candidate_measurement_only` result—never a threshold or frame-lock claim.
3. `verify` is offline. It validates the resulting receipt against the exact
   plan bytes. A separate PPU `candidate-ram recover` remains mandatory after
   every attempted execution, including a passing one.

Example after a separately authorized PPU RAM lifecycle has produced its three
private handoff files:

```sh
PPU_PY=/home/mouse9911/gits/pluto-plus-utils-starlink-qualification/.venv/bin/python
PPU_REPO=/home/mouse9911/gits/pluto-plus-utils-starlink-qualification
PRIVATE=/private/starlink-pss/15msps

"$PPU_PY" scripts/starlink_pss_hardware_probe.py plan \
  --ppu-repository "$PPU_REPO" \
  --ppu-commit 5790a39705e9e598ef048ec773e0227cf9ac1808 \
  --candidate-plan "$PRIVATE/candidate-plan.json" \
  --operation-plan "$PRIVATE/operation-plan.json" \
  --ram-receipt "$PRIVATE/ram-receipt.json" \
  --rate 15 --rf-bandwidth-hz 15000000 \
  --receipt "$PRIVATE/probe-receipt.json" \
  --output "$PRIVATE/probe-plan.json"

"$PPU_PY" scripts/starlink_pss_hardware_probe.py execute \
  --plan "$PRIVATE/probe-plan.json" \
  --ssh-password-file /private/pluto-password \
  --state-root /private/ppu-state \
  --confirm "RUN STARLINK PSS CANDIDATE 104000bac4950008230026001b440a003a 15 MSPS" \
  --output "$PRIVATE/probe-receipt.json"

"$PPU_PY" scripts/starlink_pss_hardware_probe.py verify \
  --plan "$PRIVATE/probe-plan.json" \
  --receipt "$PRIVATE/probe-receipt.json"
```

The probe never invokes DFU, loads RAM, writes QSPI, or changes the radio
personality. At 30 and 60 MS/s on the physical AD9363A, the maximum requested
RF bandwidth remains 20 MHz; those stages qualify sample-rate/FPGA processing
before any physically wider-band AD9361/AD9364 campaign.

## Ethernet-only live-LNB 15 MS/s gate

`scripts/starlink_pss_m4_live_v1.py` is the fail-closed M4 runner for the
already-qualified v7 RX-only image. It keeps continuous IQ in the FPGA and
exports only phase-map records and their candidate statistics. It does not
use or enable a transmitter.

The runner freezes three 117.5-second roles. Each role interleaves 25 receiver
LO offsets from 0 through +/-1.2 MHz in 100 kHz steps, with a 4.5-second map
observation and 200 ms settling interval at each point. The order is
`0,+100k,-100k,...` so monotonic Doppler does not alias directly into scan
order. The positive roles observe channel 4's upper 15 MHz edge at nominal IF
1,937,500,000 Hz for a 9.75 GHz low-side LNB. The middle control observes the
non-overlapping slice 50 MHz inward at 1,887,500,000 Hz.

The physical fixture must declare RX1 connected only to the powered outdoor
LNB, no transmitter, uninterrupted RAM-candidate power, Ethernet host
192.168.1.17 through `enp132s0`, exact LNB model, polarization, voltage, and
power source. The plan additionally binds the immutable RAM receipt and boot
ID, unchanged QSPI hash, exact controller binary, runner source, source
manifest, fixture bytes, and clean PPU commit.

```sh
PPU_PY=/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python
PRIVATE=/private/starlink-pss/m4-live-15
ATTEST='receiver RX1 is connected only to the powered outdoor LNB; no transmitter or attenuated bench cable is connected'

"$PPU_PY" scripts/starlink_pss_m4_live_v1.py fixture \
  --lnb-model 'EXACT MODEL' \
  --polarization horizontal \
  --lnb-supply-volts 18 \
  --lnb-power-source 'EXACT POWER SOURCE' \
  --attest "$ATTEST" \
  --output "$PRIVATE/fixture.json"

"$PPU_PY" scripts/starlink_pss_m4_live_v1.py plan \
  --probe-plan "$PRIVATE/base-probe-plan.json" \
  --controller-binary "$PRIVATE/starlink_pss_acqctl_monitor_v2" \
  --fixture-declaration "$PRIVATE/fixture.json" \
  --receipt "$PRIVATE/live-receipt.json" \
  --output "$PRIVATE/live-plan.json"

"$PPU_PY" scripts/starlink_pss_m4_live_v1.py execute \
  --plan "$PRIVATE/live-plan.json" \
  --ssh-password-file /private/pluto-password \
  --confirm 'OBSERVE LIVE STARLINK PSS 104000bac4950008230026001b440a003a CH4 UPPER 15 MSPS' \
  --output "$PRIVATE/live-receipt.json"

"$PPU_PY" scripts/starlink_pss_m4_live_v1.py verify \
  --plan "$PRIVATE/live-plan.json" \
  --receipt "$PRIVATE/live-receipt.json"
```

The positive-A/control/positive-B result must pass the frozen M3 trajectory
statistics at one or more LO points in each positive role and at no control
point. The minimum positive/control contrast is 1.10x, raw S12 rail fraction
is at most 0.0001, every in-observation transport/fault delta is zero, settings
are restored, the temporary controller is removed, and deterministic IIO
closure is mandatory. A PPU recovery receipt is required afterward. A pass is
live PSS acquisition and local timing only; SSS and frame lock remain false.
