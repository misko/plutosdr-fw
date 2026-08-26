# PlutoSDR radio-hardware pytest

This directory owns independent, guarded hardware acceptance tests, including
the refill continuity experiment for
[plutosdr-fw issue 46](https://github.com/misko/plutosdr-fw/issues/46), and a
manual/native-AGC/tandem-AUTO dual-RX tone-quality comparison. Neither imports
SPF. Public pull-request CI runs only offline metadata, continuity, planted
fault, tone-analysis, matrix-verdict, and pinned-HDL goldens; no workflow
transmits RF.

## Fixture and safety gate

Wire one authorized radio as:

```text
TX2 -> attenuation/backoff -> two-way splitter/tee -> RX0 and RX1
```

The effective attenuation from TX2 to **each** receiver must be at least 30 dB.
For every emitted level the tests enforce:

```text
physical path attenuation (dB) - TX hardware gain (dB) >= 30 dB
```

Thus a conservatively declared 0 dB physical path permits TX gains no stronger
than -30 dB. A freshly measured 30 dB physical pad permits up to 0 dB TX gain.
The test uses the AD9361/IIO names TX2, RX1, and RX2 for the physical ports the
bench calls TX2, RX0, and RX1.

The operator must provide all of the following before the test mutates TX:

- `--issue46-hardware --tx2-loopback`;
- the exact `--radio-serial` (dynamic USB coordinates are resolved from it);
- a `--firmware-pattern` matching the opened radio's `fw_version`;
- the currently justified **physical** `--loopback-attenuation-db`; the test
  combines it with the strongest requested TX backoff and requires at least
  30 dB effective attenuation;
- a manifest-pinned host libiio selected by `scripts/run_issue_46_hardware.sh`.

The runner takes a nonblocking per-serial lock. It first mutes TX1/TX2, disables
all DDS channels, and selects FPGA ZERO on all four DAC lanes. A bounded DDS
tone then qualifies both tee branches for level, clipping, and SNR. The tone is
not a continuity oracle. After that gate passes, TX1 stays muted, logical DAC
channels 2/3 select PNXX (`0x9`, P15/P20), and one DAC sync seeds the generator.
There are no later selector, sync, sample-rate, LO, or bandwidth writes during
the experiment.

Fixture teardown does not restore a possibly transmitting prior state. It
forces both TX gains below -80 dB, disables DDS, selects ZERO on every lane,
and verifies those readbacks. A cleanup failure fails the pytest session.

## Manual, native AGC, and tandem AUTO quality matrix

The quality test emits the same 100 kHz TX2 DDS tone at scale 1.0 and the same
deterministic weak-to-strong-to-weak TX gain trajectory in fresh receive
sessions. The compatibility default is the original three-cell matrix:

1. fixed 40 dB manual gain on both receivers through ordinary IIO;
2. independent AD9361 `slow_attack` AGC through ordinary IIO;
3. paired tandem `AUTO` through metadata ABI 2.

Select additional independent AD9361 comparison cells with
`--tandem-quality-native-modes slow_attack,fast_attack,hybrid`. The order is
retained in the report; every selected native mode must independently pass the
absolute quality and bidirectional gain-response gates. The legacy
`native_minus_manual`, `tandem_minus_native`, and `native_gain_evidence` report
fields continue to use `slow_attack` when it is selected, while `*_by_mode`
fields contain every requested native cell.

Release automation uses a narrower native-mode policy than this generic
comparison interface. `slow_attack` and `fast_attack` are the autonomous
release-native modes. The release-default steady-state, transient, and
modulated matrices therefore contain manual, native slow-attack, native
fast-attack, and tandem-auto cells; they deliberately exclude native hybrid.
Before entering either native mode, the runner arms the tone and applies and
reads back the weakest authorized TX2 rung while RX remains in manual mode.
This prevents fast attack from locking on a muted input and carrying a prior
run's retained lock level into the new trajectory.

Selecting `hybrid` explicitly remains supported for exploratory comparisons,
but its result is **quality-only evidence**, not an autonomous AGC or release
claim. Entering AD9361 hybrid mode can re-arm the external CTRL_IN2 control
path, and the current bench/HDL ownership path does not guard an inactive
CTRL_IN2 against a high-impedance state. An explicit hybrid selection does not
relax any configured absolute-quality or gain-response gate: gain observations
remain diagnostic, and even a passing cell is not release-eligible evidence of
autonomous gain control. This same policy applies when hybrid is explicitly
selected in the generic modulated-signal harness.

The common RX/TX LO defaults to 915 MHz. Set an explicit frequency with
`--tandem-quality-center-frequency-hz HZ`. Both LO writes are read back, the
requested and observed values are retained under `rf`, and tandem metadata
must report the kernel-selected full gain table: ID 1 through 1.3 GHz, ID 2
above 1.3 GHz through 4 GHz, and ID 3 above 4 GHz through 6 GHz.

The conservative smoke trajectory is `-61,-45,-30,-45,-61` dB. The full
trajectory is `-61,-55,-50,-45,-40,-35,-30,-35,-40,-45,-50,-55,-61` dB.
With 0 dB credited physical loss, the loudest rung remains at the required
30 dB effective-attenuation boundary. After the tandem metadata buffer opens,
AUTO is conditioned at the median of the sorted distinct trajectory gains
(`-45` dB for both profiles). This priming phase uses the normal metadata
settling proof and records its paired equilibrium, which can be below maximum on
a hotter fixture. Its TX readback, effective attenuation, convergence trace,
event summary, and final metadata are recorded under `priming`. Priming has no
tone-quality gate. The measured trajectory then starts fresh at its weak `-61`
dB rung.

The AUTO request uses qualification ADC overload thresholds `35/34` (large/
small). They exercise both decrease and recovery within the safe 30 dB TX
ceiling across the local fixture range; the production ABI defaults remain
unchanged in `metadata_abi.py`. Override them for a threshold sweep with
`--tandem-quality-large-adc-threshold` and
`--tandem-quality-small-adc-threshold`. The requested settings and firmware
threshold provenance are retained in the report.

AUTO timing defaults preserve the qualified campaign request: a 1,024-sample
power window, three low-power dwell periods, and sixteen cooldown periods.
Controlled studies can override them with
`--tandem-quality-power-measurement-samples`,
`--tandem-quality-low-power-dwell-periods`, and
`--tandem-quality-cooldown-periods`. Invalid wire ranges and timing choices
whose worst-case event count exceeds the 64-record metadata capacity are
rejected before any radio write.

Each measured level checks its actual TX gain readback before capture, drains
queued IQ, and requires three stable frames before measuring three more frames.
Native AGC stability comes from gain readback before and after each refill. Tandem
stability requires strict metadata-v5 provenance, one ownership epoch, paired
gain indices, an unchanged transition count, and no gain event in each stable
frame. There is no sleep-based settling decision.

Run one serial-attested local USB radio with the firmware already deployed:

```bash
PYTHON=/home/mouse9911/gits/spf/.venv/bin/python \
IIO_SOURCE=../libiio \
scripts/run_tandem_agc_quality_hardware.sh \
  --tandem-quality-hardware \
  --tx2-loopback \
  --radio-serial SERIAL \
  --radio-uri usb:BUS.DEVICE.INTERFACE \
  --firmware-pattern '^v0[.]41-plutoplus-spf-tandem-agc-v8-rc4$' \
  --loopback-attenuation-db 0 \
  --tandem-quality-center-frequency-hz 915000000 \
  --tandem-quality-profile smoke
```

The runner never flashes or reboots a radio. It builds/loads only the
manifest-pinned host libiio and treats the exact `fw_version` match on the
serial-attested opened context as deployment evidence. If a fresh RAM boot is
needed, perform it separately with the repository's guarded, exact-serial RAM
deployment workflow; never substitute an unrelated `build/pluto.dfu` or write
QSPI for this test.

The default report is
`build/radio-hardware/tandem-agc-quality/SERIAL/tandem-agc-quality-report.json`.
It is updated atomically after every level and contains identity and safety
attestation, convergence traces, gain/event evidence, frame hashes, per-frame
quality, per-level summaries, cross-mode numeric deltas, and final cleanup
readback. Raw IQ is retained only with `--tandem-quality-save-iq`.

Every native and tandem rung must pass the same absolute envelope: tone SNR at
least 10 dB, tone level from -70 to -3 dBFS, no clipping, cross-channel
coherence at least 0.98, within-frame differential-phase deviation at most 5
degrees, and tone-frequency error at most 250 Hz. The strongest manual rung is
the fixture/reference gate; weak manual degradation is recorded rather than
misclassified as an AGC defect. Tandem must also show paired gain indices and
prove a louder-TX gain decrease and a quieter-TX gain increase. That response
proof may use explicit events or transition-count/endpoint evidence accounted
by provider-reported frame gaps; native gain must span at least 1 dB. The report
computes tandem-minus-native/manual deltas, but initially does not claim that
one adaptive controller must numerically outperform the other: both must pass
the same absolute envelope.

## Transient attack and release analysis

`transient_quality.py` supplies the transport-independent analyzers and
`transient_hardware.py` runs a guarded weak/strong/weak TX2 trajectory in
manual, native slow-attack, native fast-attack, and tandem-auto modes. Native
hybrid is intentionally absent from the release transient matrix under the
mode policy above. Ordinary comparison cells are unchanged: they use serial
ordinary-IIO refills with the release default F=8192 and K=1, retain the first
frame around each level write instead of draining away the transition, and
qualify only returned-IQ observation spans. Release tandem uses a separate,
fixed transport: one continuous AUTO metadata session at F=65536, K=8, one
64-frame libiio batch, and a four-frame host queue. It freezes the post-open
sample counter S0 before starting the acquisition worker and targets attack at
S0+16F and release at S0+40F while the initiating batch refill remains in
flight. The worker then returns that initiating frame plus all 63 cached
replays, with no second batch or session.

Tandem retains all 64 IQ frames and raw metadata records in memory until the
buffer has closed normally. Only then does it analyze, hash, and atomically
write the mandatory 128 sidecars (64 `.cs16` plus 64 `.metadata.bin`) beneath
the serial-scoped report directory. The frozen campaign-owned envelope is
89,261,056 bytes, below a 96 MiB cap; the separately attested post-close
materialization envelope is 54,525,952 bytes and includes an 8 MiB FFT
workspace. These are bounded campaign payloads, not whole-process RSS.

Each newly opened provider stream also starts an asynchronous AD9361
temperature cache. The protected wire producer can therefore serialize exact
`INT32_MIN` until the cache is ready, unavailable, or stale; the parser exposes
that sentinel as JSON `null`. Qualification accepts `null` only as a leading
batch prefix, requires at least one exact integer in the producer range
`[-40000,125000]` mdegC, and rejects any later `null`. The runtime, production
validator, and weak-v4 durable validator independently enforce the same rule.

The release transient stimulus is explicitly `-45,-30,-45` dB; it does not
inherit the full steady trajectory's `-61` dB endpoint. Across 22
release-equivalent RC2 reports on four radios (DDS scale 1 and manual gain 40
dB), the worst individual manual-RX tone SNR at the `-45` dB rung was 24.47
dB; R18 measured at least 24.85 dB there. On R18 the same `-45` to `-30` dB
step retained native gain movement of at least 11 dB across the attack channels
and tandem moved from paired gain index 65 to 61, then returned to 65. Each
release band must first qualify these exact rungs in its steady phase. The
transient gate remains 10 dB; changing the stimulus does not relax
signal-quality acceptance.

- `timestamp_stimulus_command()` brackets every write in monotonic host time.
  Ordinary IIO only positions the write on an ordinal axis over returned IQ;
  refill/readback intervals are unobserved, so its settling spans are not
  hardware latency and cannot be ranked against tandem timing. Each tandem
  command uses the same exact primitive: attest TX1 muted, poll the coherent
  FPGA low32 counter to the frozen target, read A, perform exactly one TX2
  hardware-gain write, read the initial post-write value, then distinct B and C
  advances, defer exactly one TX2 readback until after C, and attest TX1 muted
  again. Target overshoot and the A-to-C uncertainty are each capped at 16,384
  samples. Low words are extended around the retained 64-bit frame metadata.
- `analyze_immediate_dual_rx()` analyzes fixed windows beginning at sample zero
  of each returned frame. It does not discard the transition and reports
  dual-RX tone level, SNR, clipping, differential phase, and phase stability.
- `reconcile_tandem_events()` assigns the first paired decrease/increase event
  to louder/quieter command intervals and reports conservative lower/upper
  attack and release latency bounds in samples and seconds.
- `calculate_transient_response()` requires contiguous IQ windows outside a
  command bracket. Tandem reports hardware-counter-bounded settling and a
  continuous hardware-sample observation scope. Ordinary modes report only
  spans and extrema within returned IQ windows; unobserved refill intervals can
  hide response behavior. Shared comparisons therefore null ordinary hardware
  latency fields and retain an explicit returned-IQ-only scope beside their
  diagnostic overshoot, ringing, SNR, clipping, and phase values.

The metadata provider derives `buffer_sequence` from the same FPGA sample
counter carried in `first_sample_sequence`, but it does not return exact events
or IQ for omitted frames. Transient qualification therefore rejects every
provider gap, including a matched whole-frame gap with zero transitions: it
could still hide signal overshoot or settling. Any transition-count increment
not represented by an exact in-frame event is also fatal. The retained batch is
partitioned after close into fully-pre-attack, attack-bracket,
fully-post-attack/pre-release, release-bracket, and fully-post-release groups;
the three stable groups must each contain at least eight whole frames. The
conditioning anchor is exactly the final 8192 samples of the last fully-pre
frame, and the final eight middle and release frames must be event-free,
endpoint-stable, quality-valid, and within the configured RF settling tolerance
in every 1024-sample window. Their settled gain endpoints must also prove the
command directions: the strong middle endpoint is below the weak pre-attack
maximum, and the final weak endpoint is above the strong middle endpoint.

The layer fails closed on missing sample brackets, host-write jitter over the
configured limit, excessive sample uncertainty, event-sequence holes, torn or
non-unit tandem gain steps, overlapping commands, IQ gaps outside a command
bracket, unbounded tandem-event latency, or missing baseline/steady-state
evidence. The initial weak write remains sample-unbounded because it predates
streaming; a separately labelled stable-IQ interval is the conditioning
anchor. `run_serial_transient_hardware()` owns the radio lifecycle, reloads the
report after close, and requires durable verified-cleanup evidence. Public CI
exercises only deterministic synthetic and planted-failure oracles. A passing
tandem cell fully replays all 64 frames and closes normally without cancel; any
session or shutdown failure follows mute, cancel, worker join, and close while
retaining progressive schedule and acquisition diagnostics in the invalid
atomic report.

The legacy single-target v3 transport probe remains available to qualify the
continuous larger-frame transport without producing a release PASS. It
deliberately keeps the exact RC2 device firmware while advancing only the host
to the protected RC3 libiio transport lock. It opens one AUTO metadata
session at the already-qualified `-45` dB
rung with K=8 device buffers and one 64-frame libiio batch. While the initiating
batch refill remains in flight, it reasserts the same `-45` dB level at the
frozen post-open target `S0 + 40 * 65,536` samples, then replays all 64 cached
frames. The command is accepted only with the coherent FPGA-counter A-to-B-to-C
bound, target overshoot and causal uncertainty no greater than 16,384 samples,
at least 32 fully pre-command frames, and at least eight fully post-command
frames. It never writes the `-30` dB transient rung. Returned IQ from the stable
anchor and final suffix must also meet the configured tone-level, SNR,
clipping, and phase-stability gates. A successful artifact is explicitly
transport-only and has `release_pass_eligible: false`.

The probe's AUTO request is deliberately initialized at the configured maximum
gain (`62 dB`) while the muted HOLD normalization and final manual restoration
remain at `40 dB`. At the qualified `-45 dB` weak rung this removes expected
startup INCREASE decisions: the first frame must be transition-free at the
paired maximum gain-table endpoint, and all 64 retained frames must keep
transition count zero, contain no events, and remain paired at that endpoint.
Any represented or hidden transition is still fatal. Every hardware retry must
use a fresh output directory so an earlier invalid artifact cannot be mistaken
for the new attempt.

Run the probe through the pinned-libiio launcher:

```bash
PYTHON=/home/mouse9911/gits/spf/.venv/bin/python \
IIO_SOURCE=../libiio \
scripts/run_tandem_agc_quality_hardware.sh \
  --tandem-transient-transport-probe \
  --tx2-loopback \
  --radio-serial SERIAL \
  --firmware-pattern '^v0[.]41-plutoplus-spf-tandem-agc-v8-rc2$' \
  --loopback-attenuation-db 0 \
  --tandem-quality-center-frequency-hz 915000000 \
  --tandem-quality-samples 65536 \
  --tandem-quality-output \
    build/radio-hardware/tandem-agc-transient-transport-probe
```

The durable artifact is written to
`build/radio-hardware/tandem-agc-transient-transport-probe/SERIAL/`
`tandem-agc-transient-transport-probe.json`. Its body remains
`qualified_transport_pending_cleanup` until the serial-owning wrapper closes
the radio, verifies mute/selector/DDS cleanup and identity, then atomically
promotes it to `qualified_transport`. A host loss or close failure therefore
cannot leave a final qualified artifact.

The additive v4 gate is the release preflight for the same batch transport. It
uses a separate guarded pytest marker and a fresh, isolated output namespace;
it does not replace or relax the v3 callable. From one post-open `S0`, it freezes
both `S0 + 16 * 65,536` and `S0 + 40 * 65,536` before requesting the initiating
refill. While that one refill remains in flight, it performs exactly two
same-level `-45` dB TX2 reassertions. Each command uses one hardware write,
coherent FPGA-counter A-to-initial-to-B-to-C evidence, deferred readback, and
TX1 pre/post mute assurance. The batch then replays all 64 contiguous frames
and closes normally without cancellation.

V4 independently rereads 64 exact 524,288-byte IQ sidecars and 64 exact
3,256-byte raw-metadata sidecars under
`SERIAL/transient-iq/weak_dual_target/batch/`. All frames must remain in one
stream and ownership epoch with no gaps, faults, events, or transition-count
change, and both gain indices must stay at the maximum endpoint through close.
The five-way first-command/second-command partition must contain at least eight
fully pre-first, fully between-command, and fully post-second frames. Every
1,024-sample window in the final eight frames of each stable region must stay
within 1 dB of its suffix median, and the three suffix medians must agree within
1 dB per channel. The artifact is always non-authorizing:
`release_pass_eligible` and `strong_tx_write_permitted` are both false, and it
contains no attack/release response or latency claim.

Run this distinct preflight through the same pinned-libiio launcher:

```bash
PYTHON=/home/mouse9911/gits/spf/.venv/bin/python \
IIO_SOURCE=../libiio \
scripts/run_tandem_agc_quality_hardware.sh \
  --tandem-transient-dual-target-probe \
  --tx2-loopback \
  --radio-serial SERIAL \
  --firmware-pattern '^v0[.]41-plutoplus-spf-tandem-agc-v8-rc2$' \
  --loopback-attenuation-db 0 \
  --tandem-quality-center-frequency-hz 915000000 \
  --tandem-quality-samples 65536 \
  --tandem-quality-output \
    build/radio-hardware/tandem-agc-transient-dual-target-preflight
```

Its durable report is
`build/radio-hardware/tandem-agc-transient-dual-target-preflight/SERIAL/`
`tandem-agc-transient-transport-dual-target-preflight.json`. The serial-owning
wrapper promotes the pending transport verdict only after verified radio close;
the final verdict still grants no release authority.

## Host setup and first RC2 run

Create a test-only environment; the special libiio itself is selected by the
runner rather than installed from PyPI:

```bash
python3 -m venv .venv-radio-hardware
.venv-radio-hardware/bin/pip install -r tests/radio_hardware/requirements.txt
```

Use a maintenance-window radio that is physically wired to the fixture. Do not
borrow a radio owned by a live acquisition process. The smoke command below is
expected to pass only when it actually observes RED evidence on affected RC2:

```bash
PYTHON=.venv-radio-hardware/bin/python \
IIO_SOURCE=../libiio \
scripts/run_issue_46_hardware.sh \
  --issue46-hardware \
  --tx2-loopback \
  --radio-serial SERIAL \
  --firmware-pattern 'tandem-agc-v8-rc2' \
  --loopback-attenuation-db 30 \
  --issue46-profile smoke \
  --issue46-expected red
```

Then run the pinned reproduction matrix:

```bash
PYTHON=.venv-radio-hardware/bin/python \
IIO_SOURCE=../libiio \
scripts/run_issue_46_hardware.sh \
  --issue46-hardware \
  --tx2-loopback \
  --radio-serial SERIAL \
  --firmware-pattern 'tandem-agc-v8-rc2' \
  --loopback-attenuation-db 30 \
  --issue46-profile repro \
  --issue46-expected red
```

The reproduction profile randomizes, with seed 46, the ordinary/metadata A/B
cells across kernel queue counts 1/2/4, pause factors
0/0.5/1/2/4/8/16 times `N/Fs`, and five repeats. The pinned starting point is
`Fs=2.5 MS/s`, `N=262144`, so one refill period is 104.8576 ms. Each cell reads
two frames before the pause and `K+3` after it. The default RAM sink retains IQ
only for the current cell. `--issue46-sink sync` writes and `fsync()`s every IQ
frame to expose a stalled synchronous writer; it can consume several gigabytes.

Artifacts are written below `build/radio-hardware/issue-46/`. The JSON report is
updated atomically after every cell and records the firmware/runtime identity,
fixture qualification, randomized matrix, per-frame hashes/counters/PN scores,
per-boundary verdicts, and final mute/selector readback. Use
`--issue46-save-iq` only for a bounded debugging run.

## RED/GREEN meaning

The two RX branches independently estimate the P15 phase at every returned IQ
boundary. Metadata additionally supplies the FPGA sample counter. Evidence is
invalid—not RED—if the two receivers disagree, PN confidence is weak, metadata
CRC/layout is wrong, or the counter and PN witness disagree.

- **RED:** a PN-proven gap returns through ordinary IIO; a gap occurs inside a
  conservative queue bound; metadata counts a gap without the device-overflow
  flag; or refill fails inside that safe bound.
- **GREEN:** every returned boundary is counter/PN contiguous, or saturation
  produces an exact counter gap with an explicit overflow flag, or the refill
  fails visibly outside queue capacity.

For a real regression gate, use `--issue46-expected green` (the default). The
offline planted-deletion test proves that the oracle goes RED, so a no-gap
hardware result is not accepted merely because the detector was inert.

## Localization and v0.38 comparison

After the first RED cell, rerun around its threshold, then repeat with
`--issue46-samples 131072` and `--issue46-samples 524288`. Use
`--issue46-sink sync` to test synchronous writer backpressure. USB is the
default safety boundary; an intentional IP comparison requires both an exact
`--radio-uri` and `--allow-non-usb` while still attesting the serial.

To compare v0.38 metadata-v5 on the **same radio and wiring**, boot its image in
RAM during an explicit maintenance window—never write QSPI for this test. Use a
separate libiio worktree at the manifest commit and select its manifest:

```bash
IIO_MANIFEST=manifests/libiio-frame-metadata-v5-source.yaml \
IIO_SOURCE=../libiio-metadata-v5 \
PYTHON=.venv-radio-hardware/bin/python \
scripts/run_issue_46_hardware.sh \
  --issue46-hardware --tx2-loopback \
  --radio-serial SERIAL \
  --firmware-pattern 'v0.38-plutoplus-spf-libiio-metadata-v5' \
  --loopback-attenuation-db 30 \
  --issue46-profile repro --issue46-expected red
```

The runner detects v0.38's requestless metadata constructor and RC2's required
104-byte tandem request without an SPF import. Component-level provider fixes
still need libiio unit tests; this directory remains the firmware/hardware
acceptance boundary.

## Candidate-bound lifecycle and stale-small-ADC phases

The release lifecycle runner consumes an exact candidate artifact index and
the RAM-only deployment receipt for one immutable radio serial. It does not
deploy, reboot, or flash the radio. Every path below must be absolute, the
output name must be exact and fresh beneath an owned mode-0700 directory, and
the candidate index, source manifest, DFU/FIT bytes, receipt, clean committed
harness, runtime identity, and freshly built manifest-pinned libiio must all
bind before the runner opens an IIO context.

Run the muted 64-frame lifecycle phase only after the exact candidate has been
RAM-booted and its deployment receipt is durable:

```bash
PYTHON=.venv-radio-hardware/bin/python \
IIO_SOURCE=../libiio \
scripts/run_muted_metadata_batch_lifecycle_hardware.sh \
  --hardware \
  --serial SERIAL \
  --source-manifest /absolute/candidate/source/tandem-agc-v8-rc7-source.yaml \
  --artifact-index /absolute/candidate/candidate-index.json \
  --deployment-receipt /absolute/candidate/ram-boot-receipt.json \
  --candidate-dfu /absolute/candidate/pluto.dfu \
  --output /absolute/evidence/SERIAL/muted-metadata-batch-lifecycle-v5.json
```

The v5 report can authorize only the muted lifecycle claim. It reopens the
candidate inputs and every retained metadata sidecar, revalidates close/FIFO/
fault/overflow and final mute state, and remains serial-scoped. Use a new
output namespace for every attempt.

The shared RAM deployment receipt also carries a `persistent_flash` proof:
the exact `qspi-linux` `/dev/mtdblock3` size and SHA-256 must match before and
after RAM boot. Release and lifecycle consumers validate that proof as part of
their candidate binding.

The A1.2 release-image interface observer has an intentionally different
result. It audits the committed driver, UAPI, and metadata adapter; attests the
same exact candidate and receipt; opens only the selected USB serial; forces
and verifies mute; and inventories the release's read-only tandem attributes.
It never acquires a tandem session, creates a metadata buffer, or enables TX
stimulus:

```bash
PYTHON=.venv-radio-hardware/bin/python \
IIO_SOURCE=../libiio \
scripts/run_stale_small_adc_hardware.sh \
  --hardware \
  --serial SERIAL \
  --source-manifest /absolute/candidate/source/tandem-agc-v8-rc7-source.yaml \
  --artifact-index /absolute/candidate/candidate-index.json \
  --deployment-receipt /absolute/candidate/ram-boot-receipt.json \
  --candidate-dfu /absolute/candidate/pluto.dfu \
  --output /absolute/evidence/SERIAL/stale-latch-report.json
```

A successful observer run writes a mode-0600
`plutosdr-fw.stale-small-adc-hardware.v1` report with verdict `BLOCKED` and
exits with status 2. It cannot produce `PASS`, `release_pass_eligible`, or
`hardware_qualified`. The exact release ABI exposes accepted
`SMALL_ADC_INHIBIT` events and general status, but it does not expose the
sample-aligned detector snapshot, stale-episode state, same-epoch HOLD/AUTO
control, deterministic detector injection/fixture marker, or a physical paired
pulse count independent of accepted events. Those interfaces are required to
prove the conflict, one-clear budget, recurrence/minimum behavior, and re-arm
sequence in A1.2. Until the exact release image provides a deterministic
end-to-end observation path, this report records the blocker; it does not
close it.

This observer is optional diagnostic evidence, not a release phase. The
internal stale-latch one-clear/re-arm behavior is qualified by the deterministic
RTL suite at both supported clock ratios; the release-image hardware campaign
qualifies the externally observable paired gain, lifecycle, transient,
modulated, soak, teardown, and safety behavior. A `BLOCKED` observer report
therefore neither authorizes nor blocks candidate promotion.

The candidate index's existing `harness.files` array must include exact
committed SHA-256 bindings for all of these paths; this uses the shared harness
schema without adding a new schema field:

```text
scripts/run_muted_metadata_batch_lifecycle_hardware.sh
tests/radio_hardware/candidate_binding.py
tests/radio_hardware/metadata_abi.py
tests/radio_hardware/muted_metadata_batch_lifecycle.py
linux/drivers/iio/adc/adi_tandem_agc.c
linux/include/uapi/linux/adi_tandem_agc.h
scripts/run_stale_small_adc_hardware.sh
tests/radio_hardware/stale_small_adc_hardware.py
```

Offline development uses the pure public-trace analyzer and planted oracles;
it never substitutes an inferred stale-latch PASS for missing release-image
evidence:

```bash
uv run --with pytest pytest -q \
  tests/radio_hardware/test_candidate_binding_oracles.py \
  tests/radio_hardware/test_muted_metadata_batch_lifecycle_oracles.py \
  tests/radio_hardware/test_stale_small_adc_hardware_oracles.py
```
