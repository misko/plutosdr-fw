# Paired FPGA PSS / host GLRT scanner — DO NOT MERGE firmware into main

Status: implementation started; hardware qualification is NOT complete.

## Objective and completion gate

Capture one RX at 15, then 30, then 60 MS/s while hopping over CH1L, CH2L,
CH3L, CH4L, CH1U, CH2U, CH3U, CH4U. Each visit contains exactly 120 ms of
valid samples, excluding the transition and filter-settling guard. One run
covers approximately 300 seconds of the source-sample timeline. Export a
continuous, counter-attested 2.5 MS/s CI16 pilot stream over IIO and retain
independent FPGA PSS evidence for those same visits. Analyze every valid visit
with host GLRT after recording, including visits with no FPGA trigger.

Completion requires measured live pilot evidence AND qualified FPGA PSS timing
lock, with compatible frame timing on the same observations. Transport success,
synthetic injection, a coarse periodic peak, or GLRT alone cannot complete this
goal. No detection is an admissible recording outcome, not a lock claim.
PSS timing lock is distinct from the legacy SSS-qualified `frame_lock_claim`;
SSS is not silently added to this task, nor may its legacy gate be bypassed.

## Ownership and deployment

- Firmware and firmware submodule changes stay on experimental do-not-merge
  branches; the firmware superproject is `codex/starlink-rx-only-do-not-merge`.
- Reusable PPU changes are tested, committed, and pushed to PPU remote main.
  Preserve unrelated/unqualified pending changes; never publish an untested
  firmware promotion as part of scanner support.
- Local canary: `.18`, serial `1040007c4a94000211000b009186843ef2`.
  Use serial-attested local access and reversible RAM qualification first.
- Outdoor receiver: `.17`, serial `104000bac4950008230026001b440a003a`.
  Ethernet only; deploy through PPU's qualified network-flash lifecycle, with
  exact image identities and rollback to its known-good detector firmware.
- `.17` RX1 remains on its powered 13 V, tone-off LNB/bias tee. Do not enable TX
  or assume the previous attenuated bench connection still exists.
- Do not open `.20`, `.21`, or any other radio. Acquire the serial-specific
  ownership lock before hardware work and restore settings before release.
- The existing production persistent-hop protocol deliberately excludes `.17`
  and requires dual RX. Introduce an explicit experimental single-RX capability
  and exact-serial opt-in; do not remove the legacy exclusion or impersonate
  the production FPGA/metadata identity.

## Reviewed scanner implementation

The active release selector resolved to commit
`39146ee83d00523fbd37ba02179c87a5c241a017`. Its tracked scanner plan, adapter,
target geometry, and models match the reviewed main checkout at `29be8492`.
Direct release-directory access was permission denied; the comparison used the
corresponding Git objects, not a claim to have inspected the running process.

- Leo: `src/leo/scanner/persistent_hop.py` and
  `src/leo/radio/pluto_persistent_hop.py`.
- PPU: `src/pluto_plus/persistent_hop.py` and
  `src/pluto_plus/hardware/iio_persistent_hop.py`.
- libiio commit `f6c450eada95ce99fe8756ebc244bfcf6ddcc72a`:
  `iiod/spf-hop-scheduler.c`, `spf-hop-device-local.c`, `spf-hop-session.c`.
- Kernel provider: `adi_tandem_agc.c` and the `adi_persistent_hop.h` ABI in the
  persistent-hop firmware worktree. These interfaces are not present in the
  current experimental detector kernel and require an appropriate adapter.

The host calibrates and verifies eight volatile Fast Lock slots before capture.
One IIO session remains open. A radio-local worker polls the hardware counter,
calls the owned kernel recall interface, and records before/after counter
brackets. Its sleeps are capped at 5 ms; it is not a sample-exact FPGA retune
sequencer. Valid IQ begins after the recall bracket plus the declared guard.
An independent reader and bounded writer queue decouple hopping from Ethernet
and storage. Production guidance uses a 1 ms guard, 131072-sample refills,
eight kernel buffers, eight visits of read-ahead, and a 64-visit storage queue;
the high-duty acceptance objective is at least 95%, not the historical 90% floor.
These are reference settings, not qualified values for the new image.

Fast Lock saves synthesizer calibration work. Recall return is not proof that
all analog gain/DC/filter transients have settled. Measure guard adequacy.
L/U means channel edges, not LNB polarization or 22 kHz band switching.

## Architecture and invariants

1. Keep one full-rate RX source counter running for the complete session.
2. Tap full-rate samples for sparse PSS timing. Reuse the 15 MS/s canonical
   edge-conditioning branch for coarse PSS and for the pilot export branch.
3. Translate the pilot band within that 15 MS/s stream, anti-alias filter, then
   decimate by six to 2.5 MS/s. Overall source/export ratios are 6, 12, and 24.
   The PHY remains at the full source rate; the IQ IIO device reports its own
   output rate. Do not set the AD9361 itself to 2.5 MS/s.
4. Restore only the necessary single-RX DMA path AFTER decimation. Never DMA
   the continuous full-rate IQ stream to ARM or host in normal operation.
5. Switch lower/upper mixer direction and coarse/fine coefficient banks under
   one acknowledged visit boundary. The current hard-wired upper-edge image
   cannot simply be retuned and called a lower-edge detector.
6. Fence old PSS windows and abort partial maps at each hop. Clear filter and
   detector histories without resetting the global source counter or reopening
   the IIO session. Tag every result by the visit in which its input was captured,
   not by the currently selected LO when the result is read.
7. Version the paired record contract: serial, boot/session/visit identities,
   channel/edge, actual LO/profile, frequency references, source and output
   rates, source-counter bounds, exact decimation phase and rational group
   delay, output count, coefficient/filter identities, and all invalid spans.
   Existing equal-rate, dual-RX contracts must retain their original semantics.
8. Separate intentional transition invalidity from lost samples. Neither branch
   may silently stall the ADC or conceal dropped work under backpressure.
9. Persist raw CI16 plus immutable manifests incrementally. Do not require
   compression to achieve the transport budget. Analysis runs after recording.

## Frequency and evidence limits

The existing PSS projections use rate-specific slice centers. Derive source LO,
canonical DDC translation, pilot reference, and templates from one explicit
frequency plan; do not copy the old 1.9375 GHz LO across rates. Preserve the
published pilot-bin convention separately from the scanner's historical band
reference, including any half-subcarrier difference. Account for actual LO
readback/quantization and receiver calibration before comparing CFOs.

A 2.5 MS/s output cannot cover the entire pilot band plus arbitrary +/-1.2 MHz
frequency uncertainty. Center it using an independently qualified calibration;
declare its residual-CFO coverage and filter response. If the signal may have
been filtered out, mark the GLRT comparison unobservable, not a PSS false alarm.
A separately authorized wider diagnostic recording is a fallback, not a silent
change to the requested 2.5 MS/s product.

GLRT and PSS are different detectors with different bandwidth and integration
gain. GLRT is an independent live cross-check, not an infallible truth label.
2.5 MS/s has a 400 ns sample interval; it alone cannot certify absolute 16.7 ns
PSS accuracy at 60 MS/s. Use controlled known timing and bounded full-rate debug
snippets for that gate. Debug sampling must include negatives as well as triggers.

## Schedule and throughput budget

- Per valid visit: 300000 complex output samples = 1200000 CI16 bytes.
- Continuous output: 10000000 bytes/s = 80 Mbit/s payload per radio.
- Approximately 3 GB per 300-second single-RX run, plus metadata/maps/debug.
- Eight 120 ms visits plus ideal 1 ms guards take 0.968 s per round. Actual
  recall/scheduler/startup time is additional and must be measured.
- Ideal balanced exposure is about 37.2 s per target over 300 s; this is NOT
  300 s of continuous observation of each target.
- Finish the current valid visit at the duration boundary with an explicit,
  bounded terminal overshoot; never silently truncate or claim a partial visit
  contains 120 ms. Record actual exposure and revisit gaps per target.
- Keep IQ/map/event queues bounded. Validate actual Ethernet headroom and disk
  stalls. More-frequent full maps cannot be assumed to fit beside the IQ stream.

## Stage gates

### S0 — Offline contracts and source audit

- [x] Implement this plan and a hardware-free frequency/schedule compiler.
- [x] Tests: all 24 rate/target combinations, exact 300000-sample visits,
  source/output counter mapping, LO half-Hz rounding, lower/upper signs,
  target order, reject unsupported rates/serials and impossible CFO coverage.
- [x] No radio access from the plan command; no detection claims.

### S1 — Pilot DDC oracle, vectors, and resource feasibility

- [x] Initial float/fixed-point anti-alias oracle, pinned coefficients and scaling
  for the canonical 15 -> 2.5 MS/s pilot tap. Full pilot-frame and source-rate
  composition validation remains open.
- [ ] Tests: impulses and exact group delay; both edges; tones and pilots over
  the declared CFO domain; alias rejection; clipping; decimation phase; reset
  transients; PSS/pilot frequency-reference agreement at 15/30/60 MS/s.
- [ ] Build a bit-accurate RTL DDC and matched replay vectors. Out-of-context
  and full-shell synthesis/route must demonstrate fit and timing margin with
  PSS plus the single-RX IQ DMA. Do not assume the current nearly full design
  has space, and do not count already-removed TX resources a second time.

### S2 — Paired fixed-frequency IIO capture on .18

- [ ] Add the versioned single-RX IQ/metadata path and reusable PPU reader.
- [ ] Run deterministic digital replay through both branches; the existing
  short PSS-only injection fixture does NOT prove GLRT pilot capture.
- [ ] Test split IIO buffers, exact sample counts, shared counter mapping,
  saturations, slow consumers, buffer exhaustion, cancellation, and restoration.
- [ ] Progress through short, 30-second, and 300-second transport runs. Require
  zero unexplained gaps, bounded memory, complete terminal receipts, and TX mute.

### S3 — Hop-safe dual-product recording on .18

- [ ] Adapt the proven local scheduler/recall concept to the detector's counter
  and ownership interface. Do not require the legacy tandem FPGA identity.
- [ ] Preload eight Fast Lock slots and both edge coefficient sets. Keep source
  rate and analog bandwidth constant within each 300-second run.
- [ ] Initially publish one complete 64-frame PSS map per 120 ms visit and all
  paired IQ. Explicitly discard/account for the unfinished map at the boundary.
- [ ] Tests: adjacent channels with distinguishable injected content; pulses
  immediately before/after every hop; no mixed-channel maps; no stale results;
  delayed recall; failed readback; counter discontinuity; lost events; disconnect;
  cleanup; repeated sessions without reboot. Prove the map restart limitation
  is fixed or safely avoided without weakening health gates.
- [ ] RF settling needs separate RF evidence; digital injection does not prove
  PLL/gain/DC settling. Do not assume a transmitter cable is currently available.

### S4 — Independent GLRT comparison and short-dwell PSS lock

- [ ] Run host GLRT on every valid visit, independently of FPGA candidate seeds.
  Preserve acquisition/control scores, timing/CFO uncertainties, and abstentions.
- [ ] Produce per-visit agreement, GLRT-only, PSS-only, neither, and unobservable
  classifications; compare matching time support and frequency references.
- [ ] Existing 64-frame maps take 85.333 ms; the old three-map qualification
  takes at least 256 ms and cannot be reused for a 120 ms visit.
- [ ] Replay 16/32/64-frame alternatives against frozen positives and negatives
  at equal false-alarm budgets. Version changed integration/qualification rules.
  A candidate option is three 16-frame maps in 64 ms, leaving about 56 ms for
  full-rate refinement; this is a proposal, not a sensitivity guarantee.
- [ ] Perform local candidate-to-fine handoff without an Ethernet round trip.
  Record CFO hypothesis, complete timing-search support, and matched/control
  evidence. Accumulate at candidate lags before selecting a weak-signal winner.
- [ ] Do not let post-run GLRT-guided replay masquerade as an independent online
  FPGA detection. Report diagnostic and primary results separately.

### S5 — Network deployment and live .17 qualification

- [ ] Only after .18 passes: exact-serial PPU network deployment, attested boot,
  firmware/HDL/kernel/host identities, and a tested rollback path. No USB on .17.
- [ ] First short capture, then one 300-second eight-target run at the qualified
  source rate, with 2.5 MS/s IQ and FPGA evidence from the same RX1 stream.
- [ ] Require at least 95% measured valid duty, exact valid visit lengths,
  balanced target coverage, no unexplained drops/overflow/event gaps, and exact
  restoration. Repeat runs must not require unexplained radio resets.
- [ ] Require independently qualified host pilot evidence and FPGA fine PSS lock
  with compatible timing on live observations. If there is no usable RF signal,
  report transport qualification separately; do not claim the objective complete.

### S6 — Rate ladder and final handoff

- [ ] Qualify 15, 30, and 60 MS/s source builds through the same .18-before-.17
  gates. Output remains 2.5 MS/s; separate per-rate 300-second sessions.
- [ ] Publish comparison reports with uncertainties, confusion categories,
  observed CFO coverage, duty/latency/throughput, and controlled timing errors.
- [ ] Push tested reusable PPU changes to main and all experimental source pins
  to their do-not-merge remotes. Seal artifact hashes and independent replay.

## Current progress

Read-only source review is complete. No radio has been opened, retuned, or
flashed during this scanner task. The S0 compiler and existing PSS geometry
regression suite initially passed 38 tests using PPU's Python environment. The compiler
also executes with Python `-I -S` and no third-party packages. S1–S6 remain
unqualified. The added pilot-DDC tests bring the focused suite to 76 passing
tests. A 31-tap halfband plus 255-tap divide-by-three FIR, with pinned Q17
coefficients, meets the requested 2.2 MHz passband with less than 0.01 dB ripple
and greater than 70 dB modeled stopband rejection. The Q16 mixer uses a shared
64-entry phase table; upper/lower frequency steps are +12/-13 table positions
per canonical sample. Group delay is exactly 269 canonical samples; complete
filter history spans 538 canonical samples. Tests cover both edges, arbitrary
chunk splits, explicit hop resets, ties-even arithmetic, clipping accounting,
and independent floating convolution. This is not an RTL fit or RF qualification.
