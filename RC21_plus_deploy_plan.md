# Tandem AGC v8 RC21 implementation, deployment, and verification plan

Status: active

Owner: single release operator

## Current execution update — RC32

RC21 through RC31 are immutable history. RC31 passed trusted CI build
`33101253206`, indexing, exact-serial RAM deployment, and lifecycle on the
three currently authorized Pluto+ radios. Its one authorized db696 campaign
retry was closed invalid at 4.2 GHz when native fast attack intermittently
held one RX chain's gain. Improved failure evidence and ten nonauthorizing
reproductions isolated the behavior: live-waveform 62 dB manual entry
conditioning made the mandatory fast strong-signal attack deterministic in
all ten runs, while one chain in one run did not increase gain after the
signal weakened. Local AD9361 documentation confirms that fast gain is held
after lock until a configured unlock condition fires. This is native fast-AGC
semantics, not tandem firmware behavior or a 2.4 GHz interference finding.

The active forward-only candidate is RC32. It retains the exact RC31 firmware
logic and RF plan, seeds both RX chains at 62 dB manual gain under the real
weak waveform before native fast entry, requires native fast's strong-signal
gain decrease on both receivers, and records its post-lock weak-signal gain
increase per receiver as diagnostic. Manual fixed-gain stability, slow-AGC
bidirectional response, tandem bidirectional response/event proof, every RF
quality threshold, identity, safety, and cleanup remain binding.

RC32 source lock `firmware-v1` was stopped during trusted build
`33112960920`, before artifact publication or hardware use, because its
promotion assembler still encoded the superseded four-radio count. The
forward route preserves that tag and advances to `firmware-v2`, whose
promotion contract names the exact three authorized serials and rejects the
excluded 3-8 radio or any substitution.

RC29 passed trusted build `33080376518`, indexing, four exact-serial RAM
deployments, and four lifecycle checks, but every fleet campaign attempt failed
closed and cleaned up safely. Read-only diagnostics proved three host-policy
corrections incorporated into RC30: eight stable settle frames, 48 DMA buffers only for
cooldown-zero captures, and an exact 4.2-GHz table-3 sentinel in place of the
unreliable 5.8-GHz endpoint. Binding centers are therefore 1.05, 1.55, 2.05,
and 4.2 GHz; the complete 2.45-GHz diagnostic remains mandatory with only an
isolated cleanup-verified RF-quality failure nonbinding. No device firmware,
RF threshold, transition proof, identity, safety, or cleanup gate is relaxed.

RC30 passed all 1,465 offline oracles, routed OOC, trusted integrated build
`33097467689`, deterministic packaging, checksum verification, and candidate
indexing at exact commit `aa9c56c664d5cd5f74d2c70b4e271682593f08a4`.
Its fleet-wide inventory failed closed before reboot or DFU because an
unrelated ordinary ADALM-Pluto was attached beside the four Pluto+ targets.
RC30 has zero candidate deployments and is immutable. RC31 retained the exact
RC30 firmware and RF policy and advances only the identity and pinned
`pluto-plus-utils` commit to
`b2b3113c2e8724453179f09d357b4917c0f14c77`, whose read-only inventory selects
one exact serial from a full mixed USB scan and fails closed for absence,
duplication, non-Plus selection, or incomplete identity.

Radio `1040007c4a94000211000b009186843ef2` at USB topology `3-8` is explicitly
excluded by operator authorization and must not be accessed, deployed, tested,
or counted. RC32 qualification scope is the other three local radios:
`winbond-db6968136727402c` (`3-7`), `winbond-db620818a328172c` (`5-1`), and
`104000bac4950008230026001b440a003a` (`5-2`). Final hardware qualification
remains exact-serial and one-radio-at-a-time.

Base revision: tandem AGC v8 RC20, commit
`63108b832a3618631386afdf530f19acb7905bca`

Current frequency-independent RC21 development revision:
`7cde31339249628e9130c8e9ee6ed0b5e0ccac85` (measurement-boundary and
write-on-failure evidence hardening only). The canonical frequency plan,
campaign contract, and RC21 release lineage are intentionally not yet frozen.

Historical RC21 target identity (superseded by the RC32 identity above):

- firmware version: `v0.41-plutoplus-spf-tandem-agc-v8-rc21`
- build branch: `codex/firmware-tandem-agc-v8-rc21`
- source lock: `refs/tags/tandem-agc-v8-rc21-source/firmware-v1`
- source manifest: `manifests/tandem-agc-v8-rc21-source.yaml`
- package prefix: `plutoplus-spf-tandem-agc-v8-rc21`

## 1. Objective

The original RC21 objective was to implement and qualify a release that:

1. preserves the complete immutable RC20 failure record;
2. qualifies the intended LNB intermediate-frequency range rather than relying
   on a 2.45 GHz release row whose retained weak-rung failures are consistent
   with in-chamber interference (raw IQ was not retained, so the emitter or
   protocol is not proven);
3. retains physical coverage of all three AD9361 full gain tables;
4. runs the historical 2.45 GHz matrix as required nonauthorizing diagnostic
   evidence without allowing an RF-quality failure there to stop or waive the
   binding campaign;
5. fixes the RC20 measurement-boundary false-classification risk and retains
   enough failure evidence for deterministic replay;
6. is built from an exact protected source lock, deployed to RAM with
   `pluto-plus-utils`, and passes lifecycle, full, and soak qualification on all
   four local Pluto+ radios; and
7. produces an independently replayable, hash-bound campaign index suitable
   for a promotion decision.

RC20 is never rewritten, relabeled, resumed under a different band plan, or
promoted using RC21 evidence.

## 2. Fixed safety and trust model

- The RF fixture is inside a Faraday chamber.
- Internal Wi-Fi emitters are treated as controlled test-environment inputs,
  not as harmless background.
- Both transmit chains and every DDS lane start and finish muted/off, and safe
  cleanup remains a release gate.
- Candidate firmware is deployed to volatile RAM only. No candidate operation
  may write QSPI or use `dfu-util -R` or `dfu-util -S`.
- Exact USB serial, stable topology, runtime model, boot identity, candidate
  index, DFU digest, QSPI equality, and final safe state remain mandatory
  operational guardrails.
- GitHub cryptographic attestation is not an authorization requirement. Exact
  source, artifact, harness, and evidence hashes remain reproducibility and
  wrong-target/wrong-file protections.
- Device inventory, exclusive locking, environment survey, setup, and RAM
  deployment use a reviewed, pinned, clean `pluto-plus-utils` checkout. The
  exact candidate-indexed `plutosdr-fw` harness owns qualification RF tuning,
  capture, oracle evaluation, cleanup, and release evidence. The shared
  `/home/mouse9911/gits/pluto-plus-utils` worktree must not be modified or have
  its branch changed while another task owns uncommitted work there.

## 3. Proposed canonical RF plan

The LNB assumption for the initial plan is a nominal 950--2150 MHz IF range.
The exact LNB data sheet and fixture response must be reviewed before the RC21
source lock. With that assumption, use these authorizing centers:

| Ordered key | Center | AD9361 full gain table | Role |
|---|---:|---:|---|
| `lnb-low-1050mhz` | 1,050,000,000 Hz | ID 1, 200--1300 MHz | authorizing LNB-low |
| `lnb-mid-1550mhz` | 1,550,000,000 Hz | ID 2, 1300--4000 MHz | authorizing LNB-mid |
| `lnb-high-2050mhz` | 2,050,000,000 Hz | ID 2, 1300--4000 MHz | authorizing LNB-high |
| `table3-sentinel-5800mhz` | 5,800,000,000 Hz | ID 3, 4000--6000 MHz | authorizing table-3 sentinel |

The 1.05 and 2.05 GHz points retain approximately 100 MHz of nominal margin
from the assumed LNB passband edges. The 1.55 GHz point is its midpoint. Avoid
the exact 1.3 GHz gain-table/calibration boundary.

Add one mandatory diagnostic frequency:

| Ordered key | Center | Role |
|---|---:|---|
| `diagnostic-2450mhz` | 2,450,000,000 Hz | mandatory nonauthorizing RF-quality diagnostic |

Run the same manual/native-slow/native-fast/tandem comparison at 2.45 GHz on
every radio and retain its complete report plus write-on-failure IQ evidence.
An RF-quality-only failure there is recorded as `diagnostic_failed` and the
remaining binding work continues. It cannot authorize firmware, satisfy
middle-table coverage, compensate for an authorizing failure, or enter a pass
denominator. Missing/malformed diagnostic evidence, wrong-radio or wrong-band
identity, metadata/protocol corruption, fault/FIFO/overflow, unsafe TX state,
or cleanup failure remains fatal. If a future release needs an explicit 2.4
GHz product-performance claim, that frequency must become a full authorizing
band under a controlled emitter state in a later source-locked candidate.

## 4. Stage 0 -- preserve and close the RC20 record

- [x] Verify the RC20 source tag, branch, manifest, candidate index, reports,
      and retained artifacts remain byte-for-byte unchanged.
- [x] Record every RC20 failed attempt and the approved-v7 comparison without
      converting a failure into BLOCKED or PASS.
- [x] Record the two independent RC20 findings:
  - intermittent 2.45 GHz weak-rung SNR contamination consistent with an
    uncontrolled in-chamber emitter, without claiming protocol identity where
    raw IQ was not retained;
  - a measurement-boundary oracle that can reject a normal transition hidden
    by omitted transport frames, and that discarded the exact failing frame.
- [x] Add no RC21 conclusions to immutable RC20 evidence.

The durable owner-only preservation root is
`/home/mouse9911/release-evidence/tandem-agc-v8-rc20`. It contains byte-exact
copies of the candidate/hardware tree, trusted build, OOC evidence, and
approved-v7 comparator. The external preservation manifest is
`/home/mouse9911/release-evidence/tandem-agc-v8-rc20-preservation-manifest.json`,
mode `0600`, SHA-256
`fa4d573dc9afd2436131a87fa267cf427facfd4357f0b0e8db7f735d72d631f9`.
It inventories 576 files/directories with relative paths, modes, sizes, file
hashes, exact RC20 refs/run identity, and the explicit fact that no
candidate-qualified campaign index exists. Independent full rehash and
source/copy tree comparisons passed. This preservation record is outside the
RC20 tree and does not amend or authorize RC20.

Exit criterion: an independent read-only audit can reproduce the RC20 status
and confirms that the forward work starts from immutable committed RC20. The
live repository is thereafter an explicitly active RC21 development tree and
must not be described as clean until its changes are committed.

## 5. Stage 1 -- optional chamber RF characterization

Operator decision on 2026-08-27: RC21 does not make 2.4 GHz RF quality binding
and does not require an emitter inventory or quiet-frequency selection before
the release campaign. The four authorizing centers are fixed in Section 3 and
the required nonauthorizing diagnostic is fixed at 2.45 GHz. Therefore the
complete survey protocol retained below is optional supporting work only: it
cannot block, authorize, rescore, or waive RC21, and it is not a prerequisite
for Stage 3 or the source lock. No survey result may dynamically change the
2.45 GHz diagnostic frequency within RC21.

### 5.1 Available `pluto-plus-utils` survey capability

The reviewed pinned utility currently has a dual-RX power sweep, but that sweep
does not retain raw IQ/full PSD, ordinary scan/capture lacks a shared
cross-process per-radio lock, and its local IIO open path mutes before it can
record a complete pre-state. Before any chamber survey, implement and merge a
standalone exact-serial local environment-survey workflow that:

- resolves and binds one exact USB serial and stable sysfs topology;
- acquires the same durable per-serial OS lock used by other local lifecycle
  operations;
- reads and records complete TX/DDS/DAC/tandem safe state before any mutating
  open, then explicitly ensures mute and verifies the same state after cleanup;
- performs no SSH, route, DFU, reset, reboot, or QSPI operation;
- captures bounded dual-RX raw CI16 at every declared center with fixed manual
  gain, sample rate, and RF bandwidth;
- computes and retains deterministic full PSD/STFT products plus per-artifact
  SHA-256 values instead of reducing the scan to mean/peak scalars;
- restores all RX settings and independently verifies final safe state;
- emits a strict schema-versioned local receipt/manifest; and
- supports a non-executable plan and an exact explicit execution confirmation.

Develop this in an isolated clean clone while the shared utility worktree is
owned by another task. Require offline/fake planted tests, focused/full utility
tests, formatting/lint, an independent code review, a clean commit, and a
pinned remote revision before using it on hardware. Local hashes are sufficient;
no PKI or external signing service is required.

This enabling gate is complete in production commit
`ca7c6ac9189dc3ef3bb7ab0105d170568392b777`, with cross-version test-only
follow-up `a04ac53d84849978d58a5d4c1e80c310db60530d` and stable physical-USB
inventory fix `083a077a5dfb5e2936b1300ce8ce65dbc2ec4824`. The native comparator-RAM
follow-up `7e194f66f10167954baa0dc1c8b41079edb3db03` is a direct successor;
`pluto-plus-utils` `main` resolved to that commit when it was qualified, and it
remains the required immutable execution pin for both survey and comparator
operations. Its exact local gates
are 706 passing tests with 10 explicit browser/hardware opt-in skips on Python
3.11, focused comparator tests on Python 3.11/3.12/3.13, Ruff clean, mypy clean
across 56 source files, and `git diff --check` clean. GitHub CI run
`33038655140` completed successfully at exact head
`7e194f66f10167954baa0dc1c8b41079edb3db03`, including browser and offline
Python 3.11, 3.12, and 3.13 jobs. Independent review found no P0/P1 blocker.
The inventory snapshot rejects duplicate-class-token undercount,
foreign interface symlinks, candidate-alias retargeting, and same-port device
replacement after identity capture. The implementation additionally binds the
approved plan SHA-256 at execute time, binds the imported package to the
attested clean worktree, shares the exact per-serial OS lock with candidate
lifecycle, retains pre/post shared-PHY temperature and exposed RX-attribute
provenance, restores exact settable per-RX state, atomically publishes each
center, and rejects undeclared result-tree entries. Hardware use must come from
the clean detached checkout at
`/home/mouse9911/release-evidence/tooling/pluto-plus-utils-7e194f66f101`
with its external environment at
`/home/mouse9911/release-evidence/tooling/venv-pluto-plus-utils-7e194f66f101`;
the shared worktree remains untouched.

Freeze the survey algorithm before the first capture:

- scan `2,400,000,000` through `2,490,000,000` Hz inclusive in exactly
  `1,000,000` Hz steps;
- acquire 32 windows per center and 32 additional windows at a
  `2,445,000,000` Hz drift anchor both before and after the sweep;
- after the 2.4-GHz sweep and before the post anchor, acquire 32 TX-muted
  windows at each authorizing center in exact order: 1.05, 1.55, 2.05, and
  5.8 GHz. These four records are environmental/fixture baselines only. They
  cannot waive or reinterpret an authorizing quality failure;
- use both RX channels, complex signed CI16, 65,536 samples/channel/window,
  2,500,000 samples/s, 1,500,000 Hz RF bandwidth, and exactly 40 dB manual RX
  gain;
- for every 32-window block, retain requested and actual settings immediately
  after configuration and again after its last window. Reject the block unless
  the shared RX LO is within 2 Hz of its requested center, each exposed RX
  sampling-frequency readback is exactly 2,500,000 Hz, each RX RF-bandwidth
  readback is exactly 1,500,000 Hz, both channels report manual gain-control,
  and each hardware-gain readback is within 0.26 dB of 40 dB. Do not insert
  per-window attribute reads that would change capture cadence; the bracketing
  readbacks, exact timestamps, and block artifact hashes are mandatory;
- interpret the CI16 container using the established AD9361 12-bit sample
  convention: full-scale amplitude is 2,048 and a complex sample is clipped
  when `abs(I) >= 2047` or `abs(Q) >= 2047`;
- compute a complex Welch/STFT using a 4,096-sample periodic Hann window,
  2,048-sample hop, 4,096-point FFT, `fftshift`, and 31 frames/window;
- normalize spectral density as
  `|FFT(x*w)|^2 / (Fs * sum(w^2) * 2048^2)`, average frames in linear units,
  then convert to dBFS/Hz; compute integrated power by summing
  `density * bin_width` before converting to dBFS;
- retain raw little-endian signed CI16 interleaved as
  `[rx0_i,rx0_q,rx1_i,rx1_q]`; compute STFT density and the Welch mean in
  linear units, then store their per-bin `10*log10` dBFS/Hz ordinates (not
  complex FFT coefficients) as little-endian float32. STFT layout is
  `[rx,stft_frame,fftshift_bin]` and Welch PSD layout is
  `[rx,fftshift_bin]`; zero density maps to negative infinity and the verifier
  must reproduce the exact IEEE-754 encoding;
- compute each window's integrated power in linear full-scale units, compute
  p50/p95/p99 across the 32 linear powers with
  `numpy.percentile(..., method="linear")`, and only then convert those
  percentiles to dBFS; reject a window or percentile whose integrated linear
  power is zero/nonpositive or nonfinite, so strict JSON never encodes NaN or
  infinity; retain the finite metrics, rail counts, exact shapes/dtypes, and
  artifact hashes;
- define burst occupancy per RX as the fraction of windows whose integrated
  power is strictly greater than that center's p50 plus 6 dB;
- require a private, hash-bound
  `pluto-plus-utils.environment-survey-emitter-inventory.v1` before execution.
  It contains exact top-level keys `schema`, `schema_version`, `state`, and
  `emitters`; `state` is exactly `worst-normal`. Emitter records are sorted by
  unique stable ID and bind band (`2.4-ghz` or `5-ghz`), channel, center,
  occupied closed start/stop frequencies, channel width, power setting, and
  traffic state. At least one 2.4-GHz emitter is required. For the ordered
  2.4-GHz projection require `start < stop` and reject duplicate, overlapping,
  or touching spans (`next.start <= previous.stop` fails); do not merge them.
  Bind both the canonical emitter records and derived span projection into the
  plan and receipt. Never infer authoritative spans from captured firmware
  results and never reread a changed inventory after plan approval;
- admit only integer-MHz candidate centers whose `[center-750 kHz,
  center+750 kHz]` interval does not intersect the union of any declared span
  expanded by 750 kHz, and reject an empty candidate set before hardware;
- reject any candidate clipped on any radio/RX. From exactly four semantically
  verified survey manifests and PASS receipts in this canonical serial order:
  `winbond-db6968136727402c`,
  `1040007c4a94000211000b009186843ef2`,
  `winbond-db620818a328172c`, and
  `104000bac4950008230026001b440a003a`; select one global
  center lexicographically by lowest maximum p99 integrated dBFS across all
  radio/RX paths, then lowest maximum burst occupancy across all paths, and
  finally lowest center frequency;
- compute that selection only from the predeclared worst-normal emitter-state
  sweep; emitter-off repeats are supporting diagnostics and cannot change the
  selected center; and
- require zero clipped samples in both anchors and the absolute pre/post anchor
  difference on each RX to be at most 3 dB in p99 and 0.10 in occupancy.

Each radio records the 91-center sweep, two anchors, and four authorizing-center
baselines: exactly 3,104 windows. Raw CI16 is 1,627,389,952 bytes and log-density
PSD/STFT payload is 3,254,779,904 bytes, for 4,882,169,856 bytes before
manifests. The 67,108,864-byte failure reserve makes the declared maximum
4,949,278,720 bytes, leaving 419,430,400 bytes for manifests inside the exact
5,368,709,120-byte (5 GiB) per-radio preflight. Before acquiring each hardware
lock, and again before every center, require free bytes no less than the
not-yet-written fixed payload plus the unused failure reserve and manifest
allowance. Run one serial-scoped root at a time; do not aggregate four payloads
under one free-space assumption. Retain them under the durable owner-only root
`/home/mouse9911/release-evidence/tandem-agc-v8-rc21-survey/<serial>` (root and
serial parents mode `0700`), not `/tmp`, because fleet selection needs all four
unchanged manifests and payloads. The reserve is not preallocated and may not
be silently exceeded.

1. Use a clean detached clone of a reviewed `pluto-plus-utils` commit.
2. Re-attest exact serial/topology/interface inventory and confirm no active
   deployment, scan, route lease, or RF process.
3. Force/verify TX1 and TX2 muted, every DDS raw/scale value zero, DAC selectors
   safe, tandem IDLE, FIFO empty, and faults clear before scanning.
4. Record the complete internal Wi-Fi emitter inventory, including every 2.4-
   and 5-GHz emitter, its operator-declared occupied span, channel, channel
   width, power setting, and traffic state. Prefer fixed 20 MHz channels and a
   reproducible worst-normal traffic load. The 2.4 selector uses the exact union
   of the declared 2.4-GHz spans; the 5-GHz inventory separately informs the
   5.8-GHz authorizing baseline and containment review.
5. Execute the exact frozen full survey on each of the four radios, one at a
   time and with no Pluto transmission. Retain its
   raw IQ, PSD/STFT, clipping, residual level, burst occupancy, temperature,
   exact LO readback, and file hashes.
6. Produce
   `pluto-plus-utils.environment-survey-fleet-selection.v1` from exactly those
   four manifests and the exact emitter-inventory bytes/hash. Its verifier must
   replay eligibility, fleet maxima, tie-break, and the selected per-serial/RX
   baseline lookup before any firmware result is viewed. No analyst-defined
   stability, separation, or tie-break rule may be added after capture.
7. Do not perform mandatory candidate repeats. An optional emitter-off or
   diagnostic repeat belongs in a distinct, separately preflighted,
   nonauthorizing root; it cannot alter selection, baselines, or promotion. A
   host WLAN scan is supporting context only and is not evidence of the RF
   field at the Pluto inputs.
8. A TX-muted survey cannot prove transmit containment, so separately produce
   `plutosdr-fw.rf-containment-receipt.v1` from a calibrated external spectrum
   measurement at every authorizing/control center and the maximum planned TX
   rung, plus every comparator transmit center/rung declared in Stage 6. A
   chamber certificate is sufficient only if it binds shielding loss
   versus frequency and a worst-case in-chamber source/output calculation that
   yields the same numeric maximum. The receipt must bind the leakage limit,
   measured/calculated maximum, instrument/calibration or certificate record,
   fixture, centers, and operator review. No authorizing TX may begin until it
   passes.
9. Measure or conservatively bound fixture insertion loss at 1.05, 1.55, 2.05,
   the selected 2.4 control, and 5.8 GHz, plus the comparator's exact 915 MHz
   and 2.45 GHz centers. Do not reuse an unverified scalar loss credit from a
   different center. The v7 comparator's legacy scalar is the minimum lower
   confidence bound across its 915/2450/5800 centers and both RX branches.

Exact Stage-1 contracts and artifacts:

- four serial-scoped `pluto-plus-utils.environment-survey-plan.v1`,
  `pluto-plus-utils.environment-survey-manifest.v1`, and
  `pluto-plus-utils.environment-survey-receipt.v1` records, each binding its
  plan, raw/log-density artifacts, safe-state attestations, emitter inventory,
  and exact utility revision;
- `pluto-plus-utils.environment-survey-emitter-inventory.v1`;
- `pluto-plus-utils.environment-survey-fleet-selection.v1`;
- serial-scoped raw-IQ and PSD files with SHA-256 inventory;
- `plutosdr-fw.rc21-control-baselines.v1` binding the selected-center
  per-serial/per-RX p99, occupancy, clipping, settings, emitter state, and
  artifact hashes;
- `plutosdr-fw.rc21-frequency-plan.v1` containing exact ordered names,
  frequencies, roles, gain-table expectations, Wi-Fi state, and selection
  rationale;
- `plutosdr-fw.rf-containment-receipt.v1`; and
- a human review record accepting the exact plan before any
  frequency-dependent campaign/evidence/lineage edit or RC21 source lock. The
  already completed frequency-independent Stage-2 boundary hardening predates
  this review and is recorded as such; it is never backdated.

Exit criterion: the four authorizing centers and fixed 2.45 GHz diagnostic are
accepted exactly as Section 3 records. The optional survey may be skipped. Any
subsequent frequency or authorization-role change requires a new release
candidate identity.

## 6. Stage 2 -- harden the measurement oracle

Implement a bounded, fail-closed forward fix for the RC20 measurement
boundary. It deliberately tightens direction-proof semantics for gap-hidden
transitions while preserving RF-quality thresholds:

- maintain one chronological continuity evaluator across settle, rejected
  frames, recovery settle, measurement restart, and teardown;
- distinguish adjacent frames from omitted-frame gaps using buffer and sample
  sequence deltas;
- retain strict event/counter/endpoint agreement for adjacent frames;
- never infer the exact reason or direction of a transition hidden in a gap;
- if a transition occurs after measurement begins, invalidate and retain the
  complete attempt, re-settle, and restart measurement at frame zero;
- never combine pre- and post-transition frames in one median or verdict;
- permit exactly one full measurement restart after the initial attempt
  (`_TANDEM_MEASUREMENT_RESTART_LIMIT = 1`, two total attempts); a transition
  during zero-based attempt index 1 (the second and final attempt) is
  immediately fatal as
  `tandem_measurement_transition_retry_exhausted`, while adjacent hidden
  transitions or continuity failures are fatal without consuming a restart;
- persist the pending cell, previous/current frames, phase, level, ordinals,
  buffer/sample/transition deltas, endpoint, and event list before raising;
- retain IQ and metadata for every accepted and offending frame in an abandoned
  attempt in bounded memory, and write it only after the capture/session closes,
  so evidence collection does not alter capture cadence;
- maintain a separate matrix-level write-on-failure ledger for all manual,
  native, and tandem modes. Before opening the first IIO buffer require
  `(configured_modes * trajectory_levels * measurement_frames + 1) *
  samples_per_channel * 8 <= 134,217,728`; the final term reserves one current
  offender and 8 is the dual-complex-CI16 byte stride. Retain every accepted
  measurement frame and current offending capture in memory, write no ledger
  artifact or report field on PASS, and on failure flush only after `_run_mode`
  has closed its buffer. Emit deterministic relative paths plus byte counts and
  SHA-256 inventory; bound overflow is itself fail-closed. This 128 MiB ledger
  is separate from the 32 MiB tandem abandoned-attempt detail cap and closes
  the RC20 ordinary/adaptive RF-failure replay gap;
- leave the 10 dB per-capture SNR threshold and all clipping/coherence/gain
  requirements unchanged.

Required planted tests include adjacent-frame missing events, gap-hidden
transitions, visible boundary events, multi-step/unreachable endpoints,
restart-after-accepted-frame, second-transition exhaustion, discontinuity,
epoch change, FIFO/overflow/fault, cleanup failure, and exact durable failure
payload replay.

Exit criterion: focused tests and the hardware-free radio suite excluding
commit-bound release-CLI source-attestation fixtures pass now; formatting,
lint, syntax, and independent semantic review pass; then the complete
hardware-free suite, including those source-attestation fixtures, must pass at
the eventual clean RC21 commit.

This exit criterion is complete at development commit
`7cde31339249628e9130c8e9ee6ed0b5e0ccac85`. The exact frozen implementation
is in `tests/radio_hardware/tandem_quality.py`,
`tests/radio_hardware/test_tandem_measurement_boundary_oracles.py`,
`tests/radio_hardware/test_tandem_followup_oracles.py`, and the surgical legacy
expectation in `tests/radio_hardware/test_tandem_matrix_oracles.py`. It includes
the one-restart continuity contract, separate 32 MiB tandem-detail and 128 MiB
matrix failure-IQ ledgers, atomic batch transfer, and confined no-symlink
artifact publication. Independent final review found no P0/P1 blocker. The
focused post-fix tranche passed 102 tests; an independent focused replay passed
90 and the wider tandem family passed 221. After committing the exact bytes,
the complete hardware-free radio suite, including the formerly commit-bound
release-CLI source-attestation fixtures, passed 1,002 tests with 5 explicit
hardware-only deselections. The 10 dB threshold and all RF quality limits are
unchanged.

## 7. Stage 3 -- implement the RC21 campaign and evidence contract

Operator decision on 2026-08-27 supersedes the earlier binding-environment
control design retained later in this section. RC21 keeps campaign schema v1,
uses release-hardware aggregate schema v2 to express a typed nonauthorizing
diagnostic outcome, and changes the exact default band vector to the four
authorizing centers in Section 3. The fixed 2.45 GHz work is outside that pass
denominator but remains inside the serial/candidate/host-libiio-bound full
aggregate and its complete archived evidence tree.

Implement the active RC21 contract as follows:

- full characterization, transient, modulated, and four-cycle baseline soak
  run at all four authorizing centers on every radio;
- a standalone full-profile 2.45 GHz manual/native-slow/native-fast/tandem
  matrix runs on every radio and retains its complete report and Stage-2
  failure-IQ ledger;
- an RF-quality-only 2.45 GHz FAIL is recorded as `diagnostic_failed`, includes
  exact failed cells/reasons/artifact hashes, and does not stop or rescore the
  authorizing campaign;
- missing/malformed diagnostic evidence, a fatal execution/metadata error,
  wrong serial/firmware/LO/gain-table readback, QSPI or boot-lineage mismatch,
  fault/FIFO/overflow, unsafe TX/DDS/selectors, or cleanup failure is not an RF
  quality exception and remains fatal;
- promotion computes PASS only from the four authorizing bands, but requires
  the attempted 2.45 GHz diagnostic and indexes its result verbatim; and
- reports and release notes state explicitly that RC21 makes no 2.4 GHz RF
  performance claim.

The emitter inventory, 91-center survey, selected-frequency control, pre/post
environment brackets, and their proposed schema-v2 envelope are optional
future work. They are not RC21 inputs, gates, or promotion evidence. The
following detailed design record is retained for a future release that makes
2.4 GHz binding; none of its “must” language applies to RC21.

Deferred binding-2.4 design record:

- `plutosdr-fw.tandem-agc-release-campaign.v2`;
- `plutosdr-fw.tandem-agc-release-hardware.v2`;
- `plutosdr-fw.tandem-agc-release-contract.v1`;
- `plutosdr-fw.tandem-agc-release-attempt.v1`;
- `plutosdr-fw.rf-environment-control.v1`;
- `plutosdr-fw.rf-comparator-control.v1`;
- `pluto-plus-utils.comparator-ram-plan.v1`;
- `pluto-plus-utils.comparator-ram-receipt.v1`;
- `plutosdr-fw.rf-fixture-attenuation.v1`; and
- `plutosdr-fw.operator-remediation.v1`.

The RC21 evidence chain also treats every Stage-1 contract as typed semantic
input, not an opaque hash: the emitter inventory, all four survey manifests and
receipts, fleet selection, control baselines, frequency plan, and containment
receipt named in Stage 1. The candidate-qualified index must index their exact
bytes and replay schema, source/tool revision, serial/RX lookup, selection math,
artifact hashes, safe-state result, containment limit/calibration, and the
cross-contract hashes before validating a campaign. A matching 64-character
hash without semantic replay is insufficient.

For clarity, everything from “Deferred binding-2.4 design record” through the
end of that design record is non-normative for RC21 and is not an execution
checklist. The existing candidate artifact-index and top-level
`plutosdr-fw.tandem-release-qualification` schema/version remain unchanged if
their exact top-level shape is unchanged, but their RC21 verifier must require
and replay the v2 hardware/campaign records and every v1 control, attenuation,
and remediation record. A version bump may not be hidden behind permissive
parsing.

Freeze the control producer/evaluator exactly when Stage 1 supplies the selected
center and baseline hash:

- each pre/post control records 32 ambient dual-RX windows using the Stage-1
  sample rate, RF bandwidth, manual gain, window length, ADC full-scale,
  clipping definition, Welch/STFT, percentile (`numpy.percentile` with
  `method="linear"`), and occupancy rules, and retains raw IQ plus full
  PSD/STFT and hashes;
- the following fixed-reference subphase records exactly 3 dual-RX windows at
  the same RX settings with a TX2 tone at LO +100 kHz, DDS scale 1.0, TX gain
  -30 dB, and TX1 muted; every frame must satisfy the unchanged manual
  `ToneQualityThresholds` (10 dB SNR, -70 through -3 dBFS tone, zero clipping,
  coherence at least 0.98, phase standard deviation at most 5 degrees, and
  frequency error at most 250 Hz), and pre/post tone level must retrace within
  3 dB on each RX;
- ambient p99 on each RX must be no more than that exact serial/RX path's
  Stage-1 selected-control baseline p99 plus 3 dB and occupancy no more than
  its matching baseline plus 0.10; absolute pre/post p99 drift must be at most
  3 dB and absolute occupancy drift at most 0.10 on each RX;
- any clipping, overflow, malformed/omitted artifact, identity/contract
  mismatch, reference-quality failure, or cleanup/safe-state failure yields
  `unsafe_fail`; only otherwise well-formed ambient threshold/drift excess
  yields `invalid_environment`; all checks passing yields `pass`;
- each record contains exact schema, unique control ID, envelope-attempt ID and
  ordinal, `pre`/`post` placement, serial, center/role, declared emitter state,
  candidate/frequency-plan/survey/attenuation/containment/harness hashes, the
  exact RAM-receipt SHA-256 and device boot identity, host boot ID and monotonic
  clock identity, raw
  artifact descriptors, Unix and monotonic start/completion timestamps,
  metrics, outcome, and cleanup attestation; and
- chronology must satisfy `pre.completed <= first_authorizing.started` and
  `last_authorizing.completed <= post.started`. The inclusive duration is
  `post.completed_monotonic_ns - pre.started_monotonic_ns <=
  15_000_000_000_000` for full and `<= 6_000_000_000_000` for soak; one
  nanosecond above fails.

For the fixed reference, read back and retain the requested and actual RX/TX
LO, TX hardware gain, DDS frequency, and DDS scale for every window. Exact
limits are LO error <= 2 Hz, TX-gain error <= 0.26 dB, DDS-frequency error <=
`max(2 Hz, 2,500,000/65,536 Hz)`, and DDS-scale error <=
`max(1e-6, 1/32,768)`. Define each RX tone level as the median of its three
accepted windows and compare those medians for the 3 dB retrace rule. The
pre-control must be `pass` before the first authorizing TX operation. After an
authorizing failure and safe cleanup, make one best-effort post-control when it
is safe to do so; record its result or a typed reason it could not run. That
diagnostic can improve interpretation but can never erase or downgrade the
authorizing failure.

The approved-v7 A/B uses a separate strictly nonauthorizing comparator
envelope: `pre_comparator_control`, the exact v7 comparison, then
`post_comparator_control`. Its typed `plutosdr-fw.rf-comparator-control.v1`
records bind the v7 commit/artifact/profile/harness, exact pilot serial and boot
identity, emitter/survey/frequency/attenuation/containment context, host boot
and monotonic clock identity, and safe cleanup. Comparator controls do not bind
an RC21 candidate receipt or satisfy an RC21 full/soak control. The inclusive
comparator bracket is at most 15,000,000,000,000 ns and is retained only as
nonauthorizing A/B evidence.

Comparator controls reuse the exact 32-window ambient and three-window fixed
reference acquisition, analyzer, finite-metric rules, per-serial/RX Stage-1
baseline, thresholds, cleanup, and `pass`/`invalid_environment`/`unsafe_fail`
classification defined above. They substitute the exact v7 RAM-receipt,
artifact/profile/commit/harness hashes for RC21 candidate fields. A non-`pass`
pre-control stops before comparator TX. The comparator envelope outcome is
exactly `context_pass`, `context_quality_failed`, `invalid_environment`, or
`unsafe_fail`; none is an RC21 firmware verdict. A v7 quality failure remains
`context_quality_failed`, triggers safe cleanup and a best-effort post-control,
and stops Stage 6 for RCA. A passing context requires both controls, exact
chronology, and the inclusive duration bound.

Because historical utility commit `6ebb7aa...` predates the shared flock, a
current reviewed wrapper must acquire `acquire_radio_lock(serial)` before the
pre-control and hold that one context through the unchanged historical
subprocess and post-control. The default lock root is exactly
`/tmp/pluto-plus-utils-radio-locks-${uid}` (owned mode `0700`); the file is
`radio-${sha256(serial.strip().encode("utf-8")).hexdigest()}.lock`, an owned
regular nlink-1 mode-`0600` file opened with no-follow and held by nonblocking
exclusive `flock`. A busy or malformed lock fails before hardware; no custom
lock root or waiting fallback is allowed.

- [ ] Define exact ordered `authorizing_bands` and `diagnostic_controls`.
- [ ] Generate steady, transient, and modulated authorizing phases generically
      from the four authorizing bands.
- [ ] Run the complete 11-policy steady matrix, transient phase, modulated
      phase, and baseline soak at every authorizing band on every radio.
- [ ] Give every control record an exact radio, envelope-attempt ID, center,
      emitter state, and the two ordered subphases above, then safe cleanup.
- [ ] Bracket each full campaign with exactly one pre-full and one post-full
      control, mapped only to that full interval, with no more than 15,000
      seconds between bracket timestamps.
- [ ] Bracket the entire four-cycle soak with exactly one pre-soak and one
      post-soak control, mapped only to that soak interval, with no more than
      6,000 seconds between bracket timestamps. Do not reuse a control record
      for another interval, radio, or attempt.
- [ ] Give control evaluation only the exact outcomes `pass`,
      `invalid_environment`, and `unsafe_fail`. Missing/malformed evidence or
      `unsafe_fail` is fatal; `invalid_environment` makes the mapped interval
      nonpromotable but never rewrites an authorizing firmware result.
- [ ] If the pre-control is not `pass`, stop before authorizing TX and close the
      envelope attempt with the corresponding invalid/failure outcome. If an
      authorizing phase fails, perform safe cleanup and close `failed`; a
      post-control may be absent and cannot alter that failure. Only a
      promotable passing attempt must contain the exact complete pre/post pair.
- [ ] Bind role, order, frequency, control parameters, Wi-Fi state, and fixture
      loss into plan/checkpoint fingerprints.
- [ ] Replace the single campaign-wide physical-attenuation scalar with an
      exact per-serial, per-center map. For every RX branch record measured loss
      and uncertainty; the credited loss must be no greater than the lower
      confidence bound of either branch:
      `credited_db <= min(rx0_db-rx0_uncertainty_db,
      rx1_db-rx1_uncertainty_db)`. Bind the complete map into every plan,
      checkpoint, report, resume, and evidence verifier. Every loss,
      uncertainty, and credit must be finite; measured loss and credit must be
      nonnegative; uncertainty must be nonnegative; and each lower confidence
      bound must itself be nonnegative. Reject rather than clamp an invalid
      record. The record also binds fixture ID and exact TX2/splitter/passive-
      attenuation/RX0/RX1 topology, exact serial/center/RX mapping, acquisition
      and review Unix timestamps, operator identity, and one typed provenance:
      `measured` with instrument make/model/serial, procedure ID/hash,
      calibration-certificate hash and calibration-due timestamp; or
      `conservative-bound` with ordered source-document revision/hashes and the
      replayable numeric derivation. Acquisition must be no more than 30 days
      before the first attempt using it, review must precede that attempt, and
      calibration/bound validity must extend through campaign completion.
      Reject a changed fixture/topology, expired record, mismatched mapping, or
      unsupported provenance.
- [ ] Reject arbitrary release-mode band substitution, per-radio differences,
      role changes, missing/reordered phases, or schema downgrade.
- [ ] Remove the fingerprint-bound ghost 915 MHz fallback in
      `release_cli._base_quality`; derive the canonical base explicitly.
- [ ] Preserve the separate lifecycle campaign's existing 915 MHz contract.
- [ ] Add the environment-control harness and its verifier to the exact archived
      harness inventory.
- [ ] Index and semantically replay every Stage-1 contract and comparator
      control; reject a missing survey receipt, wrong baseline serial/RX,
      changed emitter projection, changed containment calibration/limit, or
      hash-only placeholder.
- [ ] Make control integrity mandatory while computing promotion solely from
      authorizing bands.
- [ ] Make the release CLI's per-radio full and soak envelopes—not individual
      matrix phases—the sole owners of controls and outer retries. A full
      envelope contains its pre-control, every steady/transient/modulated
      authorizing phase, post-control, and cleanup; a soak envelope contains
      pre-control, all four soak cycles, post-control, and cleanup.
- [ ] Preserve append-only envelope-attempt history. Each full or soak envelope
      gets at most two attempts: the initial attempt and one explicitly
      authorized fresh retry. The retry requires a durable
      `operator-remediation.v1` record binding the prior `failed`,
      `invalid_environment`, or `abandoned_interrupted` attempt-result hash,
      diagnosis, remediation, unchanged candidate/plan, operator, and time.
      Any firmware, harness, band, attenuation, or policy change requires a new
      RC instead.
- [ ] Use exact attempt outcomes `pass`, `failed`, `invalid_environment`, and
      `abandoned_interrupted`; a blocked precondition occurs before an attempt
      and is not converted into one. A deliberately stopped `pending`
      checkpoint may resume only inside the same unchanged envelope attempt and
      only while its pre-control time ceiling remains valid; completed phases
      may be revalidated and skipped only there. A process rediscovered in
      `running` state closes as `abandoned_interrupted` and requires the one
      remediation-bound fresh attempt. A failed or environmentally invalid
      phase also ends its envelope attempt. The fresh attempt reruns the entire
      envelope with new controls and no reused phase results. No per-cell or
      nested per-phase retry is allowed. Promotion must index every failed,
      invalid, abandoned, and passing envelope attempt in monotonic order and
      reject deletion, overwrite, selected-success trees, mixed-attempt phase
      reuse, or an unbound retry.

The sole exception to the phrase "no per-cell retry" is the zero-based Stage-2
measurement-boundary recovery inside one tandem cell execution: attempt index
0 may be abandoned once, followed by one contiguous re-settle and attempt index
1. It is not an outer cell/phase/envelope rerun, never mixes accepted frames,
and its complete abandoned-attempt evidence remains inside the same immutable
phase report. No other internal retry is permitted.

For every indexed qualification-harness hardware invocation—including smoke,
lifecycle, full, and soak—the outer wrapper acquires the exact shared plus-utils
serial lock before opening IIO and holds it until final cleanup/report closure.
This outer lease is the sole shared-lock owner; inner `Issue46Radio` retains its
private harness lock but must not reacquire the shared lock. Full/soak controls
and all child phases execute under the one outer lease. A busy/malformed shared
lock fails before hardware. This prevents any plus-utils survey/setup/deploy
from racing a qualification harness even though the two projects retain
distinct internal locks.

Primary files expected to change:

- `tests/radio_hardware/release_campaign.py`
- `tests/radio_hardware/release_cli.py`
- `tests/radio_hardware/tandem_quality.py`
- `tests/radio_hardware/release_contract.py`
- a dedicated `tests/radio_hardware/rf_environment_control.py`
- `scripts/run_tandem_agc_release_hardware.sh`
- `scripts/run_rc21_rf_environment_control_hardware.sh` for diagnostics only;
  promotable controls remain owned by the release wrapper
- `scripts/tandem_release_device_plan.py`
- `tests/test_tandem_release_device_plan.py`
- `scripts/tandem_release_evidence.py`
- `scripts/check_tandem_release_offline.sh`
- `tests/radio_hardware/test_release_campaign_oracles.py`
- `tests/radio_hardware/test_release_cli_oracles.py`
- `tests/radio_hardware/test_rf_environment_control_oracles.py`
- `tests/radio_hardware/test_release_contract_oracles.py`
- `tests/radio_hardware/test_tandem_measurement_boundary_oracles.py`
- `tests/radio_hardware/test_muted_metadata_batch_lifecycle_oracles.py`
- `tests/test_tandem_release_evidence.py`
- `tests/test_tandem_rc21_release_route.py`
- `scripts/ci/package_main_firmware.sh` (exact candidate harness inventory)
- `.github/workflows/firmware-main.yml`
- `manifests/tandem-agc-v8-rc21-source.yaml`
- `tests/radio_hardware/README.md`
- `RELEASING.md`
- `RELEASE_NOTES.md`
- `KALMAN_GITHUB_RUNNER.md`
- `tandem_AGC_fw_plan.md`

Cardinality for four radios:

- full steady: 4 bands x 11 policies x 4 radios = 176 matrices;
- soak: 4 cycles x 4 bands x 4 radios = 64 matrices;
- transient: 4 authorizing band reports per radio;
- modulated: 4 authorizing band reports per radio;
- lifecycle remains separate; and
- one fixed 2.45 GHz full-profile diagnostic matrix per radio is mandatory,
  archived, and nonauthorizing; it is not one of the 176 authorizing steady
  matrices.

Budget assumptions and hard ceilings:

- observed RC20 steady acquisition was approximately 22.2 seconds/matrix;
  four authorizing bands therefore project about 16.3 minutes of steady
  acquisition per radio before transient/modulated overhead;
- retain the existing 4-hour full-campaign deadline per radio and 90-minute
  soak deadline per radio; do not increase either after observing a failure;
- the four-radio no-retry deadline ceiling is 22 hours for full+soak alone; if
  every permitted full and soak envelope retry were consumed, the hard
  retry-inclusive ceiling is 44 hours before deployment/lifecycle/control
  overhead. Run strictly one radio at a time and report actual elapsed time
  against both figures;
- the optional environment survey, if separately requested later, retains its
  exact 5 GiB preflight; every active campaign root requires a source-computed
  upper bound plus 512 MiB free reserve before capture; and
- tandem diagnostic/save-IQ deferred writes share one 32 MiB bound per tandem
  capture session/mode, while the matrix-wide write-on-failure ledger is capped
  at 128 MiB; both are implemented by Stage 2 and neither may be used as an
  unbounded logging path.

Exit criterion: exact plan/replay oracles require the ordered four-band
authorizing vector, reject any missing/reordered/substituted authorizing band,
require one serial/firmware-bound fixed-2.45 diagnostic per radio, prove that
an RF-quality-only diagnostic failure does not enter the pass denominator, and
prove that missing evidence or any diagnostic safety/integrity failure remains
fatal. Attenuation inflation/substitution, missing attempts, attempt
reordering, unbound retries, and selected-success histories remain rejected.

## 8. Stage 4 -- advance immutable lineage to RC21

- [ ] Create the RC21 source manifest with the same external source graph as
      RC20 unless a reviewed implementation dependency truly changes.
- [ ] Add the protected RC21 workflow, package, offline-check, and evidence
      routes while retaining RC20 reproduction mappings.
- [ ] Add `tests/test_tandem_rc21_release_route.py`.
- [ ] Update active release notes, releasing guide, runner handoff, hardware
      README, and the main tandem plan with truthful RC20 history and RC21
      requirements.
- [ ] Run source-graph equality and protected-route tests.
- [ ] Commit the frozen implementation on the release branch.
- [ ] Rerun commit-bound archive/source-blob tests at the clean commit.
- [ ] Push the release branch, RC21 build branch, and protected source-lock tag
      only after all local gates and an independent diff review pass.

Exit criterion: local and remote RC21 branch/tag resolve to one exact clean
commit; RC20 branch/tag remain unchanged.

## 9. Stage 5 -- trusted build and candidate evidence

- [ ] Run official OOC verification at the exact RC21 commit.
- [ ] Dispatch the protected owner workflow with the exact RC21 version.
- [ ] Require the exact identity guard, build/package, deterministic inventories,
      and artifact upload to succeed.
- [ ] Verify outer artifact digest, bundle ordering, inner checksums, DFU/FIT,
      source manifest/graph, packed versions, integrated route/timing/policy,
      OOC evidence, and exact harness bytes.
- [ ] Assemble `candidate-pre-hardware` evidence and verify it from both the
      live repository and a fresh detached exact-commit clone.

Exit criterion: one candidate index and exact DFU pass independent semantic
verification. No hardware may consume an unverified artifact.

## 10. Stage 6 -- pilot comparator, then final RC21 RAM deployment

Inventory, setup, comparator deployment, and RC21 RAM deployment use
`pluto-plus-utils` from a pinned clean checkout. The indexed qualification
harness owns its own bounded RF tuning/capture operations as stated in the
trust model.

### 10.1 Required comparator-RAM utility gate

This gate is complete in native `pluto-plus-utils` production commit
`7e194f66f10167954baa0dc1c8b41079edb3db03`. The legacy release-candidate
command/receipt is not relabeled or translated into comparator evidence. The
released implementation:

- provides `firmware comparator-ram plan`, `execute`, and `receipt-verify` with
  exact `pluto-plus-utils.comparator-ram-plan.v1` and
  `pluto-plus-utils.comparator-ram-receipt.v1` contracts and confirmation
  `COMPARATOR RAM BOOT <serial>`;
- binds the retained approved-v7 DFU/FIT/profile, exact pilot
  serial/topology/interface, expected current runtime, shared per-serial lock,
  sealed DFU bytes, paired selector, owned `/32` route, boot identities, QSPI
  equality, and complete cleanup/safe state, while rejecting `-R`, `-S`, and
  every persistent target;
- rechecks the exact operator-approved plan and absent receipt under the shared
  radio lock, then rechecks the plan at the sealed-DFU mutation boundary, so a
  changed plan or queued duplicate exits before target/route/hardware access;
- passed success, mutation, wrong-radio, stale-plan, duplicate-executor,
  QSPI-change, route/lock, cleanup, and no-receipt planted tests; and
- is pushed to `pluto-plus-utils` `main`; GitHub CI run `33038655140` passed
  browser and offline Python 3.11/3.12/3.13 jobs at that exact head.

The final local gate is 706 passing tests with 10 explicit browser/hardware
opt-in skips, focused multi-version comparator tests, Ruff, formatting, mypy
across 56 source files, clean-checkout source attestation, and independent
P0/P1 review. The execution pin is the clean detached checkout
`/home/mouse9911/release-evidence/tooling/pluto-plus-utils-7e194f66f101`
with external environment
`/home/mouse9911/release-evidence/tooling/venv-pluto-plus-utils-7e194f66f101`.
Its clean source attestation binds source-tree SHA-256
`81588a219ad8c50e720acfb9a00c771ab65ace5c09d42292ad8ca0f4126fb751`
and wrapper
`/home/mouse9911/release-evidence/tooling/pluto-plus-utils-7e194f66f101/src/pluto_plus/comparator_ram.py`
(45,913 bytes, SHA-256
`d99cd28f025c924f64b4b7bc4775f3ae06404a4463db8441a5e1b8afb9041590`).
No comparator plan has yet been generated and no comparator hardware operation
has occurred.

- [ ] Reserve one pilot and, before any RC21 receipt exists, run the exact
      approved-v7 artifact/tag comparison in a separate nonauthorizing root,
      after the comparator RAM receipt and before the final RC21 deployment.
      The comparator matrix is exactly the historical `radio qualify-tandem`
      operation at ordered
      centers 915,000,000, 2,450,000,000, and 5,800,000,000 Hz, profile
      `tandem-agc-v7-release-ram`, strong TX gain -10 dB, weak TX gain -60 dB,
      and the conservative scalar attenuation credit defined in Stage 1. Its
      implementation is pinned to `pluto-plus-utils` commit
      `6ebb7aab092468cb89e75191190d7db5262f6801`; no current utility behavior may
      be silently substituted. Bind tag
      `v0.40-plutoplus-spf-tandem-agc-v7`, commit
      `e0049c2d0077770eeb1f6850b957878a373623d9`, retained artifact hashes, and
      exact comparator harness. The retained approved bundle SHA-256 is
      `5468827aa7eca6badd69a518df6bf70ef4220e3f39cdca66b7ba8e3fb452fbb4`,
      DFU SHA-256 is
      `4fe286f9756e3c721d5322ba9c18831f43ab4678c34bb9ef7f238cbb1236debe`,
      and FIT-body SHA-256 is
      `4c19876d09082adfdbd255726e84be397eb4e18a4c0d96b9722d7d543c2ebae7`.
      The later historical v7 manifest is an artifact record, not a source-lock
      file contained in that tag.
- [ ] After the comparator-RAM utility gate is complete, use that newly pinned
      utility to create a
      non-executable `pluto-plus-utils.comparator-ram-plan.v1` bound to the
      pilot serial/topology, current firmware, profile, and exact durable DFU at
      `/home/mouse9911/release-evidence/tandem-agc-v8-rc20/approved-v7-comparator/plutoplus-spf-tandem-agc-v2-e0049c2d0077-pluto.dfu`.
      Review it, then execute only with confirmation
      `COMPARATOR RAM BOOT <serial>`. The guarded transaction uses the selected
      interface's exact owned `/32` route, password-only/no-known-host SSH,
      `dfu-util -d 0456:b673,0456:b674 -p <topology> -a firmware.dfu -D
      <sealed-fd>` followed by the same selector/topology/alternate with `-e`,
      and never `-R`, `-S`, or a QSPI/persistent target.
- [ ] Require `pluto-plus-utils.comparator-ram-receipt.v1` PASS before the
      comparator matrix. It binds the plan/profile/DFU/FIT hashes, exact
      current clean plus-utils commit and source-tree hash, exact comparator
      wrapper path/bytes/hash,
      serial/model/topology/interface, distinct pre/post boot IDs, expected v7
      firmware and ABI, pre/post `qspi-linux` name/size/SHA equality, paired
      DFU commands, released `/32` route, and complete final safe state. A
      failed or missing receipt blocks the comparator and no RC21 evidence may
      reuse its boot epoch. The plan binds the same current utility/wrapper
      identities before execution. Index and semantically replay these exact
      executable identities, receipt, and comparator report.
- [ ] State explicitly that this same-board run is fresh A/B context, not a
      replay or extension of approved-v7 qualification, and that unsupported
      RC21-era oracle/schema differences are non-equivalent.
- [ ] Finish the comparator's cleanup and safe-state checks before proceeding.
      Its boot/receipt epoch must never be reused as RC21 evidence.
- [ ] Re-capture strict USB inventory after the comparator and immediately
      before RC21 planning.
- [ ] Confirm exact serial/topology/model/current firmware and safe state.
- [ ] Produce and review a non-executable plan bound to the candidate index and
      DFU.
- [ ] Verify no pre-existing owned `/32` route, receipt, or competing lock.
- [ ] Execute the exact confirmed RAM transition.
- [ ] Require receipt PASS, new boot identity, RC21 firmware/model, unchanged
      QSPI name/size/SHA, exact paired DFU selector, released route, and final
      safe state.
- [ ] Never overwrite an existing valid receipt or power-cycle between receipt
      and qualification.

Exit criterion: one pilot has a valid replayable RAM receipt and safe RC21
runtime after the comparator is complete; no later v7 boot or power cycle is
permitted until that pilot's RC21 qualification finishes. All other radios may
already have participated in the TX-muted Stage-1 survey, but receive no
comparator boot, firmware deployment, or qualification operation in Stage 6.

## 11. Stage 7 -- pilot comparison and qualification

Use fresh immutable roots. The in-chamber Wi-Fi state is recorded as context,
not used to select a frequency or rescore a result.

1. Revalidate the RC21 receipt and boot identity without rebooting.
2. Run RC21 all-frequency smoke.
3. Run RC21 lifecycle.
4. Invoke the full aggregate once. It runs all four authorizing bands for
   steady/transient/modulated work, then the fixed full-profile 2.45 GHz
   diagnostic last. A safe `diagnostic_failed` result is complete and does not
   stop the aggregate; any other diagnostic failure is fatal.
5. Invoke the four-cycle, four-authorizing-band baseline soak once. It contains
   no 2.45 GHz diagnostic and does not consume any prior phase evidence.
6. Verify teardown, TX mute, DDS zero, selectors safe, tandem IDLE, FIFO empty,
   faults clear, exact runtime identity, and no host `/32` route.

Do not rerun an individual cell or choose a new frequency after a failure.
Resume only an explicitly incomplete steady checkpoint whose exact fingerprint
and artifacts revalidate. A failed authorizing phase stops for RCA and explicit
operator direction; no automatic retry is part of RC21. The sole continuation
exception is the typed, safe, fully retained 2.45 GHz `diagnostic_failed`
outcome.

Exit criterion: the pilot passes every authorizing phase, completes and indexes
the 2.45 GHz diagnostic under the policy above, and independent review finds no
measurement/evidence ambiguity.

## 12. Stage 8 -- all-four-radio campaign

Reserved exact serials:

- `winbond-db6968136727402c`
- `1040007c4a94000211000b009186843ef2`
- `winbond-db620818a328172c`
- `104000bac4950008230026001b440a003a`

The successful Stage-7 pilot is radio 1 of 4 and its exact receipt/full/soak
evidence is reused as that radio's sole authorizing attempt; do not redeploy or
rerun it. Select each of the remaining three exact serials once, one at a time,
and:

- plan and RAM-deploy with `pluto-plus-utils`;
- validate the exact receipt;
- run lifecycle, then one full aggregate and one soak aggregate; the full
  aggregate owns all authorizing phases plus the fixed nonauthorizing 2.45 GHz
  diagnostic, and both aggregates own safe cleanup;
- preserve every attempt and checkpoint; and
- independently audit runtime identity, route absence, and safe state before
  moving to the next serial.

Exit criterion: all four exact serials pass the identical four-band authorizing
matrix, each has a complete indexed 2.45 GHz diagnostic, every receipt
validates, and no radio has a persistent candidate write.

## 13. Stage 9 -- final evidence and promotion decision

- [ ] Assemble the candidate-qualified campaign index from the verified
      candidate parent and exact hardware tree.
- [ ] Verify every indexed file, receipt, authorizing phase report, 2.45 GHz
      diagnostic report/IQ ledger, harness
      byte, source lock, and candidate identity.
- [ ] Replay verification from a clean detached exact-commit checkout.
- [ ] Compare RC21 against the approved v7 physical evidence and RC20 failures,
      clearly separating exact-oracle equivalence from supporting context.
- [ ] Record known limitations: LNB IF characterization is conducted-loop
      AD9361/AGC evidence, not LNB bias, LO, DiSEqC, satellite-link, or antenna
      qualification unless those elements are explicitly added.
- [ ] Promote only if every authorizing requirement passes and no evidence,
      safety, identity, or reproducibility blocker remains. A typed
      `diagnostic_failed` at 2.45 GHz does not block; it must be disclosed and
      excludes any 2.4 GHz RF-performance claim.

Final success statement must identify the exact commit, source lock, workflow
run, bundle/DFU/FIT/index hashes, four serials, frequency plan, campaign-index
hash, and independent verifier result.

## 14. Stop conditions

Stop before build, deployment, or promotion when any of these occurs:

- frequency or role is still undecided;
- LNB passband or fixture loss is not reviewed;
- required free-space or bounded-evidence preflight fails;
- shared `pluto-plus-utils` state is dirty/unowned and no clean pinned clone is
  available;
- source, branch, tag, manifest, package, or evidence identity disagrees;
- any commit-bound, hardware-free, OOC, integrated, or semantic verifier fails;
- artifact/index/DFU bytes differ from the reviewed hashes;
- a target serial/topology/model is ambiguous;
- a route, lock, prior receipt, or competing hardware process is present;
- QSPI equality or final safe state cannot be proved;
- attempt history is missing/reordered or a failed authorizing attempt is
  silently retried/replaced;
- the 2.45 GHz diagnostic is missing, malformed, loses its required failure-IQ
  evidence, or fails for anything other than a cleanup-verified RF-quality
  evaluation; an isolated typed `diagnostic_failed` is explicitly not a stop
  condition;
- an authorizing phase fails without completed root-cause analysis; or
- independent verification disagrees with the producing tool.

The response to a stop condition is diagnosis and a new explicit gate. It is
never weakening an oracle, deleting evidence, changing frequency after seeing
results, or silently starting the next radio.
