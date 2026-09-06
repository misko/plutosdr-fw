# FPGA PSS tracker: gated 15/30/60 MS/s implementation plan

Status: experimental, RX-only, and **DO NOT MERGE INTO FIRMWARE MAIN**.

This document is the canonical execution plan for implementing, testing,
deploying, and verifying the FPGA PSS timing tracker. Work advances through
15 MS/s, 30 MS/s, and 60 MS/s gates. A later stage may reuse an earlier stage,
but it may not weaken or bypass an earlier acceptance criterion.

## 1. Objective

Build an RX-only FPGA acquisition and tracking path that:

1. searches continuously for the selected Starlink PSS hypothesis;
2. reduces the full-rate IQ stream to bounded timing maps and candidate records;
3. establishes repeatable PSS phase on a live LNB signal;
4. refines timing to one source-sample resolution at 30 and 60 MS/s; and
5. exports only compact results and health telemetry over Ethernet.

PSS acquisition, PSS tracking, SSS detection, and final frame lock are separate
claims. No stage may describe a correlation peak as frame lock until the later
cadence and SSS gates exist and pass.

## 2. Non-negotiable boundaries

- Target only radio serial `104000bac4950008230026001b440a003a`.
- Resolve that serial to its current direct USB topology immediately before
  every mutation. The last verified topology was `5-2`; topology is not a
  substitute for serial identity.
- Do not touch `.20`, `.21`, or any radio owned by another process.
- Keep TX absent from experimental FPGA builds where possible. Otherwise keep
  every TX channel at `-80 dB`, keep TX buffers disabled, and power down the TX
  LO when the runtime permits it.
- Experimental HDL, firmware, launchers, and waveform policy stay on
  `codex/starlink-rx-only-do-not-merge` and identically marked submodule
  branches. They are never merged or cherry-picked into firmware `main`.
- Experimental images remain RAM-only. Never write an experimental PSS image
  to QSPI.
- Reusable waveform-independent PPU improvements are developed from current
  PPU `main`, tested, reviewed, merged to PPU `main`, and recorded by commit in
  later receipts. Do not copy PPU logic into the experimental firmware tree.
- Every hardware operation retains identity, configuration, safety, result,
  and restoration evidence in a machine-readable receipt.

## 3. Hardware and configuration truth

The authorized radio is physically attested as an AD9363A. It is now
persistently configured with the `ad9361-1r1t` Linux driver personality and one
RX stream.

That configuration changes driver policy; it does not change the RFIC die.
The current measurement established:

- a `60,000,000 Hz` RX-bandwidth request reads back as `56,000,000 Hz`;
- a `60,000,000 S/s` sample-rate request reads back as `60,000,000 S/s`;
- 60 MS/s sampling and 60 MHz analog bandwidth are different claims; and
- greater-than-20-MHz RF bandwidth remains out of specification on this
  physical AD9363A.

Initial 15/30/60 MS/s engineering trials therefore use an RF bandwidth at or
below 20 MHz. A qualified wideband pass requires a separately serial-attested
physical AD9361/AD9364 and a measured RF-response test.

Relevant evidence:

- PPU setup receipt:
  `/home/mouse9911/pluto-state/starlink-rx-only-dnm/setup-ad9361-1r1t-20260906/state/setup/receipts/e1ded32ce93644efbfe8b1274a13a204.json`
- bandwidth/sample-rate receipt:
  `/home/mouse9911/pluto-state/starlink-rx-only-dnm/setup-ad9361-1r1t-20260906/bandwidth-probe-receipt.json`

## 4. Architecture

Use one canonical 15 MS/s continuous acquisition engine at every stage. At
higher input rates, feed it through deterministic decimation and add a sparse
full-rate tracker:

```text
15 MS/s: full-rate PSS search -----------------------> phase map

30 MS/s: anti-alias /2 -> canonical 15 MS/s search -> coarse phase
          original 30 MS/s --------------------------> sparse fine phase

60 MS/s: anti-alias /2 -> 30 MS/s -> /2 -> 15 MS/s -> coarse phase
          original 60 MS/s --------------------------> sparse fine phase
```

Do not scale the phase-map memory to 40,000 or 80,000 bins. Keep the proven
20,000-bin map at the canonical rate. Once acquisition identifies a credible
phase track, schedule fine correlation around predicted PSS locations in
future frames. The repeating signal removes the need for an 85-ms full-rate
BRAM history.

DDR history is an optional diagnostic fallback, not the primary tracker
architecture.

## 5. Phase-map contract

At 15 MS/s:

- nominal frame period: 20,000 samples, approximately 1.333333 ms;
- map width: 20,000 timing-phase bins;
- score: one normalized PSS correlation value per accepted sample position;
- accumulation: sum matching phase bins over 64 nominal frames;
- samples represented by one map: 1,280,000;
- observation time per map: approximately 85.333 ms;
- payload per map: 20,000 unsigned 16-bit values, 40,000 bytes; and
- normal publication rate: approximately 11.71875 maps/s.

Every published map carries at least its bank, generation, absolute start
sample index, accepted/discarded counts, discontinuity counts, and all detector,
scheduler, FIFO, arithmetic, read, release, and overrun health fields.

## 6. Stage 0: make continuous observation operational

### Implementation

1. Admit the explicit `ad9361-1r1t` runtime target in the DNM PSS launcher while
   retaining exact serial/topology, approved-image, TX-safe, and rollback gates.
2. RAM-boot the existing 15 MS/s acquisition candidate and verify recovery now
   returns to persistent `ad9361-1r1t` rather than the former AD9363A target.
3. Implement a continuous PS-side map consumer that:
   - waits for either completed ping-pong bank;
   - snapshots immutable map identity and health counters;
   - reads all 20,000 values;
   - releases that exact bank immediately;
   - rejects generation changes, stale reads, duplicate releases, and gaps; and
   - writes append-only candidate/health records.
4. Send full maps or summaries over Ethernet. Never require continuous raw-IQ
   transfer for acquisition.
5. Treat the current 32-bit counters as saturating, not wrapping. The 15 MS/s
   accepted-score counter has enough headroom for this 120-second gate. Before
   a 60 MS/s soak, add a versioned 64-bit or explicitly clearable observation
   counter; a host cannot reconstruct samples hidden after hardware saturates.

### Test

- Unit-test bank selection, generation adjacency, saturated-counter rejection,
  delayed reader, duplicate map, missing map, and malformed telemetry handling.
- Run a 120-second hardware soak with no RF detection requirement.
- Deliberately stall the reader in a separate negative test and prove the
  overrun/discard counters detect it.

### Gate 0 pass

- approximately 1,406 complete maps in 120 seconds;
- zero discarded scores and zero map overruns during the normal soak;
- zero discontinuity, FFT, kernel, product, scheduler, index, protocol,
  arithmetic, FIFO, map-read, or map-release faults;
- bounded Ethernet traffic, approximately 0.47 MB/s for complete maps; and
- verified recovery to the unchanged QSPI image and persistent radio target.

## 7. Stage 1: qualify 15 MS/s PSS acquisition

### Implementation

Keep the routed v6 full-rate detector geometry:

1. accept continuous 15 MS/s complex IQ;
2. compute the selected matched-filter score at every sample position using
   overlap-save FFT processing;
3. normalize and quantize the score deterministically;
4. fold consecutive scores modulo 20,000 samples;
5. accumulate 64 frames into each phase map; and
6. calculate candidate statistics on the PS first.

For every map calculate:

- strongest phase and score;
- runner-up outside a declared guard region;
- median and median absolute deviation;
- peak-to-background ratio and peak prominence;
- local peak shape; and
- phase movement relative to preceding maps.

Track a slowly moving, unwrapped phase trajectory. Do not require a genuine
signal to remain in one fixed bin; sample-clock error and motion can create a
steady phase slope.

### Verification ladder

1. Bit-exact HDL simulation with known PSS placement, amplitude, noise, and CFO.
2. FPGA deterministic sample injection with timing at bin zero, map boundaries,
   wraparound, and randomly selected phases.
3. Cabled RF from one otherwise unused SDR through verified attenuation; do not
   transmit over the air and do not interrupt radios owned by another process.
4. Outdoor LNB observation over Ethernet.
5. Off-channel negative control.
6. Repeat the positive observation.

### Outdoor 120-second record

Record:

- LNB model, LO frequency, polarization, sideband and spectral inversion;
- requested and read-back RF LO, bandwidth, sample rate, gain mode and gain;
- clipping/rail statistics and RSSI;
- map/candidate stream with absolute sample indexes;
- all health counters before, during, and after the dwell; and
- exact firmware, HDL, coefficient, template, PPU, plan, and receipt hashes.

If the PSS location or CFO is uncertain, scan a bounded list of receiver-LO
offsets using a complete dwell and receipt per setting. Do this before adding
many parallel FPGA CFO banks.

### Gate 1 pass

- injected timing is correct within one 15 MS/s sample, approximately 66.7 ns;
- a cabled-RF signal produces the declared phase trajectory and disappears in
  the negative control;
- a live candidate is significant against the predeclared map background test,
  persists across consecutive maps, and repeats in a second dwell;
- the off-channel control does not produce an equivalent candidate track; and
- the Stage 0 continuity and safety gates remain closed.

Gate 1 claims PSS acquisition and candidate timing only. It does not claim SSS
or final frame lock.

## 8. Stage 2: add 30 MS/s acquisition and refinement

### Implementation

1. Capture the source at exactly 30,000,000 S/s with read-back clock evidence.
2. Add a deterministic 2:1 anti-alias/half-band lane feeding the unchanged
   15 MS/s detector.
3. Define and test the exact mapping:

   ```text
   source_index_30 = 2 * canonical_index_15 + filter_delay + decimator_phase
   ```

4. Preserve filter coefficients, passband, stopband, group delay, rounding,
   saturation, reset, and discontinuity behavior as versioned contracts.
5. After coarse acquisition, arm a bounded direct 30 MS/s correlator around
   predicted PSS positions in subsequent frames.
6. Export only the fine peak, nearby scores, source index, CFO hypothesis, and
   health metadata.

### Test

- Compare the decimator bit-for-bit with a software fixed-point oracle.
- Sweep every input parity and timing position around the PSS boundary.
- Compare coarse decisions with a separately generated 15 MS/s reference.
- Compare fine timing with a direct 30 MS/s software correlator.
- Test candidate loss, false candidate, phase wrap, discontinuity, and
  reacquisition.
- Repeat simulation, FPGA injection, cabled RF, and 120-second live tests.

### Gate 2 pass

- coarse decisions agree with the canonical 15 MS/s oracle;
- translated absolute indexes include exact filter delay and decimator phase;
- fine timing agrees within one 30 MS/s source sample, approximately 33.3 ns;
- sustained 120-second processing has zero unexplained loss or faults; and
- the current physical AD9363A result is labeled an at-most-20-MHz narrowband
  sample-rate trial, not a full-band pass.

## 9. Stage 3: add 60 MS/s acquisition and refinement

### Implementation

Reuse the validated 30 MS/s stage:

```text
60 MS/s -> half-band /2 -> 30 MS/s -> half-band /2 -> 15 MS/s detector
    `------------------------------------------------> sparse 60 MS/s tracker
```

1. Parameterize and route the source interface for exactly 60,000,000 S/s.
2. Reuse the validated first half-band stage and add the second stage rather
   than creating an unrelated monolithic 4:1 path.
3. Define the complete source-index transform, including both filters' group
   delays and both decimation phases.
4. Keep the 20,000-bin canonical coarse map unchanged.
5. Schedule a bounded full-rate 60 MS/s tracker only around future predicted
   PSS positions.
6. Evaluate only the declared timing and CFO neighborhood; do not instantiate
   an 80,000-bin map or a blind full-rate bank per CFO hypothesis.
7. Widen or add explicitly resettable observation counters before this gate.
   The present DDC accepted counter saturates after about 71.6 seconds at
   60 MS/s; host-side polling cannot recover the hidden count after saturation.

### Test

- Prove each half-band stage separately, then prove their cascade.
- Compare the cascaded output bit-for-bit with a software oracle.
- Sweep all four source-sample phases mapping to one canonical sample.
- Compare fine timing with a direct 60 MS/s software correlator.
- Verify scheduler margin, BRAM/DSP/LUT use, setup/hold timing, CDC inventory,
  resets, discontinuities, and sustained flow.
- Repeat injection, cabled RF, and 120-second live tests at no more than 20 MHz
  RF bandwidth on the authorized physical AD9363A.

### Gate 3 pass

- canonical acquisition agrees with the 15 MS/s oracle;
- absolute source-index mapping is exact across phase and frame wrap;
- fine timing agrees within one 60 MS/s source sample, approximately 16.7 ns;
- the routed design closes timing with positive setup and hold slack;
- a 120-second run has no unexplained counter, FIFO, scheduler, map, or stream
  loss; and
- the result is explicitly separated from any claim of 60 MHz analog
  bandwidth.

## 10. Candidate and lock policy

Thresholds are declared before live data is inspected. At minimum, a PSS
candidate requires:

1. peak significance against robust within-map background statistics;
2. adequate separation from a runner-up outside the peak guard region;
3. a plausible local peak shape;
4. continuity along a bounded phase/slope trajectory across several maps; and
5. absence of an equivalent track in the negative control.

After a candidate is established, the fine tracker predicts subsequent PSS
locations and records misses as well as hits. Loss of the bounded trajectory
returns the state machine to acquisition; it must not coast indefinitely.

Only after live PSS timing is repeatable should a later plan add:

- CFO-bank refinement;
- PSS cadence lock;
- SSS hypothesis testing;
- joint PSS/SSS consistency; and
- a formally named frame-lock state with acquisition/loss hysteresis.

## 11. Deployment and recovery

The experimental FPGA image is volatile:

1. inspect and lock the exact radio;
2. verify no conflicting owner;
3. attest persistent `ad9361-1r1t`, QSPI hash, TX safety, and current settings;
4. RAM-boot the exact approved DNM candidate over USB;
5. re-attest serial, topology, runtime identity, RX-only surface, and TX-safe
   state;
6. keep power uninterrupted when moving to Ethernet-only outdoor operation;
7. run the bounded observation;
8. stop and collect artifacts; and
9. reboot to QSPI and verify persistent `ad9361-1r1t`, firmware hash, settings,
   TX safety, IIO availability, and receipt completeness.

A power loss outdoors returns the radio to QSPI baseline. It is not permission
to persist the experimental image.

## 12. Milestones

| Milestone | Required result |
| --- | --- |
| M0 | DNM launcher safely admits persistent `ad9361-1r1t` |
| M1 | Continuous 120-second map reader with zero normal-run loss |
| M2 | Repeatable simulated/injected 15 MS/s PSS timing |
| M3 | Repeatable cabled-RF 15 MS/s timing and negative control |
| M4 | Repeatable live-LNB 15 MS/s candidate trajectory |
| M5 | Proven 30-to-15 MS/s decimator and exact index mapping |
| M6 | Sparse 30 MS/s fine timing within one source sample |
| M7 | Proven cascaded 60-to-30-to-15 MS/s path |
| M8 | Sparse 60 MS/s fine timing within one source sample |
| M9 | Repeated live 60 MS/s narrowband result and rollback proof |
| M10 | Separate PSS cadence, SSS, and final frame-lock qualification |

## 13. Stop/go rule

Advance only one gate at a time:

```text
M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9 -> M10
```

At every failure, preserve the receipt and classify it as identity, safety,
transport, continuity, detector, RF, threshold, or recovery. Fix the earliest
failed layer and repeat that gate; do not compensate for an unexplained lower
layer by tuning a later detector threshold.

The immediate implementation target is M0 followed by M1. The existing FPGA
detector has already demonstrated sustained 15 MS/s score generation and map
publication. The next useful result is a lossless 120-second consumer, not a
new correlator.
