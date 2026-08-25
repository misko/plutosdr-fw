# PlutoSDR radio-hardware pytest

This directory owns two independent hardware acceptance tests: the refill
continuity experiment for
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
  --firmware-pattern '^v0[.]41-plutoplus-spf-tandem-agc-v8-rc2$' \
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
mode policy above. The runner uses one kernel buffer and retains the first
frame around each level write instead of draining away the transition. A
bounded acquisition-only thread keeps metadata refills active while tandem TX
writes execute. IQ analysis, hashing, and optional artifact writes are deferred
until the buffer is closed; the default worst-case retained IQ is about 6 MiB
and every configuration is capped at 64 MiB.

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
  hardware latency and cannot be ranked against tandem timing. Tandem reads the
  coherent low 32 bits of the same FPGA counter used by metadata immediately
  before and after the TX write. The upper bound is accepted only after two
  distinct advances beyond the initial post-write read: a word already in the
  closed-loop CDC path can explain the first, while the second is causally
  post-command. Low words are extended around nearby 64-bit frame metadata.
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
not represented by an exact in-frame event is also fatal.

The layer fails closed on missing sample brackets, host-write jitter over the
configured limit, excessive sample uncertainty, event-sequence holes, torn or
non-unit tandem gain steps, overlapping commands, IQ gaps outside a command
bracket, unbounded tandem-event latency, or missing baseline/steady-state
evidence. The initial weak write remains sample-unbounded because it predates
streaming; a separately labelled stable-IQ interval is the conditioning
anchor. `run_serial_transient_hardware()` owns the radio lifecycle, reloads the
report after close, and requires durable verified-cleanup evidence. Public CI
exercises only deterministic synthetic and planted-failure oracles.

Before another loudness-step transient attempt, the dedicated transport probe
can qualify the proposed larger-frame transport without producing a release
PASS. It opens one AUTO metadata session at the already-qualified `-45` dB
rung, requires 32 consecutive 65,536-sample frames with K=2, then reasserts the
same `-45` dB level while streaming and requires eight more consecutive frames.
The command is accepted only with the coherent FPGA-counter A-to-B-to-C bound,
at most six queued/bracketed frames, and at least two fully post-command frames.
It never writes the `-30` dB transient rung. Returned IQ from the stable anchor
and final suffix must also meet the configured tone-level, SNR, clipping, and
phase-stability gates. A successful artifact is explicitly transport-only and
has `release_pass_eligible: false`.

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
