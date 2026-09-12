# Fresh coarse-PSS / inspection-stream release

Experimental branch: `codex/pss-coarse25-do-not-merge` (firmware and HDL).
Never merge this firmware into main. This is a new architecture, not a restart
of the stopped shared-FFT timing-closure experiment.

## Authority and timebox

User authorized implementation, testing, deployment and verification on the
previously allocated radios. Foundation feasibility started 2026-09-12
05:32:24 UTC; midpoint 09:32:24 UTC; hard review 13:32:24 UTC (eight hours).
Do not silently extend this budget or substitute simulation for deployment.
If a gate fails, retain evidence and report the specific failed gate before
expanding the architecture or weakening acceptance.

Only these serials are in scope:

| Role | Address | Exact serial | Deployment |
| --- | --- | --- | --- |
| Bench canary | .18 | 1040007c4a94000211000b009186843ef2 | PPU, reversible test first |
| Outdoor receiver | 192.168.1.17 | 104000bac4950008230026001b440a003a | Ethernet PPU only |

Acquire PPU's shared serial lock and attest identity before radio operations.
Do not use .14, .20, .21 or an additional transmitter. .17 RX1 is attached to
the powered 13 V, tone-off LNB/bias tee; never enable its TX. Preserve pinned
SSH trust, current firmware receipts and rollback before mutation. Reusable
PPU changes belong on its main, with isolated tested commits; preserve its
existing unrelated dirty changes.

## Small architecture

One RX -> rate-specific conditioning -> accepted 2.5 MS/s CI16 stream, forked
to independent IIO/DMA IQ export and a small direct coarse-PSS correlator.
The detector cannot backpressure IQ. Explicit epochs, sample counters, filter
delay, gaps, overflow and candidate validity are part of the interface.
No native fine-search or shared FFT/controller in this foundation.

CI16 payload is 10,000,000 bytes/s (80 Mbit/s), before transport overhead;
300 s requires 3 GB. Measure the actual Ethernet/IIO path; do not infer
continuous throughput from a short buffered capture.
2.5 MHz / 750 Hz is 3333 1/3 samples, not 3333. Use rational frame phase and
retain the native-source index mapping when scaling rates.

## Gates, in order

### C0: prove the coarse detector, offline

Freeze `tools/starlink_coarse25.py`'s evaluation configuration and source
hashes before reading evaluation outcomes. Use the exact existing fixed-point
15 -> 2.5 MS/s filter for recorded-capture replay, including its full delay,
history and sample phase. This derivative is not proof of an AD9361's 2.5 MS/s
analog response. Independently test the later radio response before deployment.

Direct PSS correlation, bounded CFO hypotheses, exact rational frame phase;
no GLRT timing or same-window CFO seeding. Existing narrow-band pilot GLRT
results do not pass this gate. Real data labels are historical observations,
not absolute RF timing truth. Keep fractional timing, noise-only, CW and
discontinuity controls separate from positive tests.

Initial screening acceptance, fixed before evaluation:
- Synthetic noiseless PSS must recover frame phase within one 2.5 MS/s sample
  across six canonical decimation phases and CFOs -300, 0, +300 kHz.
- Positive held-out recordings at 36.5 s and 37.0 s: each 120 ms, blind coarse
  phase agrees with independent saved pilot timing within 2 us, peak z >= 8.
- Historical negative controls at 1.0 s and 1.5 s: no peak z >= 8.
- Search covers -400 to +400 kHz in 100 kHz steps. No claim outside this
  bounded envelope. Template/filter mismatch and drift limitations must be
  reported, not silently corrected using labels.
- Noise/CW rejection and reproducibility tests must pass before accepting a
  detector design. Two real negatives do not establish a false-alarm rate.

First screen is deliberately a feasibility test, not a production threshold
qualification. Freeze any subsequent larger statistical qualification before
running it; a failed screen requires a decision, not retrospective retuning.

### C1: 2.5 MS/s transport foundation

Minimal RX-only full-board build; detector absent or disabled. Verify routed
setup and hold timing, valid clock constraints, resources and RX calibration.
Deterministic accepted-stream injection proves byte order, continuity, resets,
gap accounting and stop/restart. Capture 120 ms then 300 s over IIO and measure
actual transport throughput. Preserve enough receipts to replay independently.

### C2: add coarse PSS

Budget DSP/BRAM/cycles before RTL. Reuse arithmetic, local pipeline control;
route the complete board, not just a favorable isolated kernel. Compare RTL
fixed-point scores and reported source indices against a separately computed
oracle, including saturation, reset, overrun and detector-drop cases. Confirm
enabling detection never alters or stalls the inspection IQ stream.

### C3: deploy and verify

PPU serial-attested .18 canary, rollback, 300 s capture, result/IQ replay
agreement and clean stop/restart. Only then deploy a pinned package over
Ethernet to .17 and record a fixed-frequency 300 s outdoor test. Run blind
host GLRT over the exported IQ and compare detection/miss/false-candidate
evidence. No signal means RF efficacy remains unverified, not a false pass.

### C4: scale one rate at a time

| RX MS/s | Output MS/s | Decimation |
| --- | --- | --- |
| 2.5 | 2.5 | 1 |
| 5 | 2.5 | 2 |
| 15 | 2.5 | 6 |
| 30 | 2.5 | 12 |
| 60 | 2.5 | 24 |

For each: freeze anti-alias/filter specification; test passband/alias rejection,
gain, delay and exact index mapping; qualify full-board routing and actual RX
rate/calibration; repeat 300 s IQ/detector comparison. Do not require a specific
factor ordering until its resource and filter design is checked. Roll back to
the last qualified rate on failure.

### C5: separate later releases

120 ms valid dwells, eight high/low targets over 300 s with explicit settling
and epochs; then bounded native-rate fine timing/CFO refinement. A 60 MS/s RX
feeding a 2.5 MS/s correlator is not native 60 MS/s fine-search deployment.

## Checkpoint ledger

- 05:32 UTC: new authorization; fresh FW/HDL worktrees created from preserved
  bases 44bef794eb0f72d1cd3726f182328d7a8c4e94df and
  0b4bf2f0fd8c58c79852266b07f9e95770f75f36. No radio changed.
- Plan frozen before fresh detector evaluation. C0 pending; C1-C5 not started.
