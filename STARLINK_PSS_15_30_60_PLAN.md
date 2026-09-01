# Starlink PSS 15/30/60 MS/s RX-only development plan

Status: experimental, RAM-only, and **DO NOT MERGE INTO FIRMWARE MAIN**.

Target radio: `104000bac4950008230026001b440a003a` only. A USB address, serial
TTY, network interface, or `usb:B.D.I` URI is never accepted as identity by
itself; every hardware operation must re-resolve and lock the serial plus USB
topology immediately before use.

## Governance and merge boundary

PPU remains generic product tooling. Reusable PPU work is reviewed, tested,
and merged to PPU `main` so radio setup and release evidence do not become an
untracked experiment. PPU may model, plan, attest, and receipt explicit AD936x
driver/channel targets:

- `ad9361-2r2t`: legacy/default Pluto+ behavior;
- `ad9363a-1r1t`: native constrained driver and one digital RX stream;
- `ad9361-1r1t`: wider AD9361 driver limits and one digital RX stream.

Those names attest the requested and observed Linux driver profile and stream
geometry; they do not claim to identify the physical RFIC die. PPU must remain
waveform-agnostic and contain no Starlink-specific detector policy.

All Starlink waveform, detector, RX-only HDL/Linux, build, and radio-trial work
stays on `codex/starlink-rx-only-do-not-merge` and identically marked submodule
branches. Branch protection must reject a pull request from this branch to
firmware `main`. Experimental artifacts may be tagged and retained, but the
branch is never merged to firmware `main`.

## Fixed geometry and rate strategy

The native waveform model is 240 MS/s, 1024 useful samples, 32 samples of
inverted prefix, and a 750 Hz frame rate. Its exact integer projections are:

| RX/DMA rate | Native-rate useful/prefix/symbol | Samples/frame | Detection-lane rate | Decimation | Detection symbol |
|---:|---:|---:|---:|---:|---:|
| 15 MS/s | 64 / 2 / 66 | 20,000 | 15 MS/s | 1 | 66 |
| 30 MS/s | 128 / 4 / 132 | 40,000 | 15 MS/s | 2 | 66 |
| 60 MS/s | 256 / 8 / 264 | 80,000 | 15 MS/s | 4 | 66 |

The 30 and 60 MS/s stages preserve full-rate RX DMA. Only an independent PSS
detection lane is decimated to 15 MS/s. Its filter, integer phase, group delay,
rounding, and saturation are part of the versioned oracle, and its event index
must map exactly back to the full-rate RX timestamp. This keeps one qualified
66-sample correlator while allowing full-band recordings and later algorithms
to retain all input samples.

A tracked result can be produced after a predicted PSS window plus correlator
pipeline latency. Initial acquisition is different: host bootstrap must first
collect and search enough data to establish template, sideband, CFO, phase,
and 750 Hz cadence. No sub-symbol acquisition-latency claim is made. Once
locked, four-frame confirmation spans about 5.33 ms and eight frames about
10.67 ms, plus pipeline and host/FPGA handoff latency.

## What the 15 MS/s evidence says

The provenance-bound capture
`cap-20260831T071200-9184cf0ad6cc` is a real 15 MS/s, 1.1875 GHz, upper-edge
recording. It came from another radio, so it is algorithm evidence, not
qualification of the target radio.

Exact PSS template replay found the first timing evidence at about 6.9 s,
reported candidates in 27 of 237 blocks, evaluated 3,665 windows on a 750 Hz
lattice, and produced robust peak z-scores with median 7.227 and maximum
9.876. This is compelling evidence for exact-template-plus-cadence acquisition,
subject to independent false-alarm controls and target-radio confirmation.

The repeated-delay lag metric did not behave as a useful PSS trigger on the
same real data. Across 210 known template-window starts in the first capture
chunk, the metric had median 0.0162 at the exact start; even the best value in
a +/-66-sample neighborhood had median 0.0540 and maximum 0.255. The committed
threshold of 0.75 therefore produced no events. Lowering the threshold is not
a remedy: at 0.05, background exceeded the threshold for about 5.72% of all
windows and formed 39,813 excursions in that chunk.

Consequently:

- the repeated-delay monitor is diagnostic/status plumbing only;
- its threshold remains immutable at 0.75 for this revision;
- structural positive fixtures must trigger it, while the recorded real PSS
  fixture is explicitly expected not to trigger it;
- a lag event is never reported as PSS, frame alignment, or acquisition; and
- failure of the lag monitor to fire on a live signal is not a reason to lower
  its threshold or weaken a test.

## Detector architecture

1. Preserve formatted RX0 I/Q, full-rate timestamps, DMA data, continuity, and
   overflow reporting independently of all detector logic.
2. At 15 MS/s, acquire with the existing host golden search: exact lower/upper
   PSS templates, explicit CFO hypotheses, deterministic tie handling, and
   multi-frame 750 Hz cadence. Refine the nine CFO banks across repeated-frame
   evidence, then lock one block-selected CFO for local frame tracking. Do not
   maximize nine banks independently on every frame; that changes the oracle
   and preferentially selects noise.
3. Hand only bounded predicted windows to a candidate-gated FPGA exact
   correlator. The engine supports 65 trial lags `[-32,+32]` and 66 template
   taps. Normal one-CFO tracking is 3,217,500 complex tap-MACs/s. An explicitly
   commanded three-bank check is 9,652,500, and an all-nine diagnostic is
   28,957,500. Blind acquisition remains on the host. A three-DSP, one-complex-
   tap-per-cycle engine has ample scheduling margin at 100 MHz; generated OOC
   and full-route reports, not this arithmetic, decide acceptance.
4. Deliver the exact engine in two steps. First publish all 65 raw
   `{lag,index,C_re,C_im,Ex,Eh}` tuples for one host-selected Q1.15 coefficient
   bank so the host can reproduce every score and tie. Then add the exact
   normalized reducer, nine-bank one-lag CFO refinement, adjacent-bank checks,
   and trace mode. Coefficients are host-quantized with round-to-nearest,
   ties-to-even, digest- and CRC-bound, and never synthesized by a runtime NCO.
   The engine reports candidate measurements only; multi-frame alignment and
   false-alarm policy remain on the host.
5. For 30 and 60 MS/s, feed the same correlator through independently qualified
   x2 and x4 detection-lane decimators while preserving full-rate DMA.
6. Keep the 0.75 repeated-delay monitor as an AXI-readable integration aid for
   enables, valid gaps, index jumps, counters, and clock-domain crossing. It is
   not upstream of the exact correlator and cannot suppress exact searches.
7. Begin SSS only after PSS timing, sideband, CFO convention, cadence, and
   false-alarm behavior have passed at the current rate. Start SSS in the host;
   move it into FPGA only if profiling shows a justified bounded workload.

An autonomous full-stream blind FPGA search is deliberately deferred. If host
bootstrap is later unacceptable, compare an overlap-save FFT correlator or a
separately proven coarse stage against the same recordings and negative
controls as a new reviewed scope. The repeated-delay metric is not promoted to
that role without new evidence.

### Stage-15 exact-engine contract

The first exact engine runs at 100 MHz and captures exactly 130 tagged samples
around each predicted center: `p-32` through `p+97`. Each output names the
stored raw timestamp at its first tap; no timestamp is reconstructed from
pipeline latency. Disable, FIFO overflow, or a nonconsecutive accepted index
flushes the job and increments a visible abort counter.

A three-DSP Gauss complex multiplier issues one exact tap per engine clock.
CI16 samples and coefficients produce signed 33-bit complex taps accumulated
without loss in signed 48-bit real and imaginary sums. Sample energy uses 38
bits, committed coefficient energy is constrained below 31 bits, and exact
normalized-score comparison uses wide rational cross-products rather than a
divider or floating point. The same three DSPs are time-multiplexed for a
bounded sample-energy prepass and coefficient-commit validation before the
one-tap-per-clock complex loop; the design does not quietly assume two extra
squaring multipliers. The raw-result milestone precedes the winner reducer so
its arithmetic can be checked independently.

The exact engine receives a distinct 16 KiB AXI aperture at `0x79040000`; the
diagnostic monitor remains read-only at `0x79030000`. Its versioned ABI has
separate `TRACK_ONE`, `CFO_REFINE`, `VALIDATE_BANKS`, and `SINGLE_SHOT_TRACE`
modes, shadow/active coefficient banks, commit generation and validation
status, double-buffered results, and processed/aborted/overrun counters. A
configuration becomes active only after host readback, SHA-256 verification,
CRC/energy validation, and an idle-boundary generation acknowledgement.

The initial measured-budget target for the exact correlator, control, and
result block is at most 3 DSP48E1s, 5 BRAM36 equivalents, 2,500 LUTs, and 2,000
registers. Detection-lane DDC resources at 30/60 MS/s are budgeted separately.
Every number remains provisional until both OOC and complete Zynq-7010 route
reports exist.

The 21-DSP repeated-delay monitor is temporary integration instrumentation. It
may remain beside the exact engine at 15 MS/s only while the full routed shell
retains the declared headroom. It is compile-time removed before allocating an
x2/x4 detection lane if it would crowd the useful exact correlator or DDC; no
PSS function depends on keeping it.

## Current implementation evidence

The existing wide-arithmetic repeated-delay diagnostic core has these Vivado
2022.2 post-synthesis out-of-context results at a common 16.666 ns constraint.
They prove neither exact-PSS sensitivity nor full-design routing closure:

| Rate geometry | LUT | FF | LUTRAM | DSP48E1 | Synth WNS |
|---:|---:|---:|---:|---:|---:|
| 15 | 1,597 | 907 | 434 | 21 | +3.523 ns |
| 30 | 1,878 | 921 | 564 | 21 | +3.523 ns |
| 60 | 2,001 | 915 | 694 | 21 | +3.523 ns |

These figures are retained as diagnostic-baseline evidence. The new exact
correlator and x2/x4 detection lane require separate OOC and full-shell reports.
No resource or timing estimate is substituted for a generated report.

The integrated 15 MS/s diagnostic-monitor shell was rebuilt locally with
Vivado 2022.2 after the geometry, independent-arithmetic fixture, and scoped
bus-skew checks were fixed. It used 6,417/17,600 LUTs (36.46%), 9,187/35,200
registers (26.10%), 1,012/6,000 LUT-memory cells (16.87%), 3/60 BRAM tiles, and
49/80 DSPs. Setup WNS was +1.277 ns, hold WHS was +0.016 ns, and all 15,945
nets routed. The monitor mailbox had +8.019 ns max-delay slack and +8.238 ns
bus-skew slack, with exactly 293 CDC-15 payload rows, two CDC-3 toggle rows,
and no new critical crossing. The routed-checkpoint SHA-256 was
`c81e64767b02ca1a535f487a6dc7c64df7f497d975623c064f94f479ac069f9e`.
This is implementation evidence for diagnostic plumbing, not PSS-detection or
radio qualification.

A frozen CI16/Q1.15 one-bank tracking model has also been replayed over all 210
first-chunk real windows using the oracle's actual upper-edge, `-100 kHz`,
local-radius-30 semantics. It selected the identical integer lag in 210/210
windows. Fixed-versus-float normalized-score absolute error was at most
`1.52e-5`, with median `3.49e-6`. In contrast, allowing each frame to maximize
all nine CFO banks across the proposed 65-lag `[-32,+32]` aperture retained the
block-selected `-100 kHz` bank in only 97/210 windows. These results freeze the
acquisition-versus-tracking split and form a predeclared Stage-15 equivalence
target.

The trusted full-shell run `33540748707` at parent commit `829380e76240` and
HDL source `091f8d5852fa` also completed implementation and produced a fully
routed RX-only checkpoint. It used 4,429/17,600 LUTs (25.16%), 7,173/35,200
registers (20.38%), 3/60 BRAM tiles (5%), and 28/80 DSPs (35%). Routed setup
WNS was +2.049 ns and hold WHS was +0.006 ns, with zero setup and hold failing
endpoints. Both remaining RX timestamp-FIFO bus-skew constraints were met at
+8.997 ns and +9.413 ns. Packaging then stopped because its inherited policy
expected four RX-plus-TX FIFO constraints; the RX-only shell intentionally has
only the two RX crossings.

Replacement trusted run `33542849550` at parent commit `c9c0c72c1b52` passed
the complete build and packaging workflow with the same routed checkpoint and
source graph. Its outer archive and both internal SHA-256 manifests have been
independently verified. It remains explicitly hardware-untested and is a
comparison baseline, not the detector image to boot. The first radio-eligible
candidate must be rebuilt from the later, source-locked monitor/exact-engine
commit and consumed by the merged PPU v2 RAM-qualification path.

## RX-only shell and common qualification gates

The experimental shell compiles `MODE_1R1T=1`, disables the AD936x FPGA DAC
datapath and TDD logic, removes TX DMA/packer/interpolation, removes tandem AGC,
removes the second PS high-performance port, and holds the digital TX pins
static. Linux disables the absent TX DMA/DDS/TDD/tandem devices, selects 1R1T,
and skips TX digital-interface tuning.

Every rate must pass all of these common gates:

- source closure: immutable parent/submodule commits, tool versions, waveform
  and template digests, generated-image hashes, and reproducible commands;
- functional closure: bit-exact oracle agreement for score, hypothesis, index,
  timestamp mapping, ties, overflow, saturation, zero energy, valid gaps,
  enable changes, index jumps, wrong cadence, and negative recordings;
- implementation closure: actual RX-only Zynq-7010 full implementation with
  setup and hold WNS >= 0, TNS = 0, THS = 0, no critical DRC, no unconstrained
  detector clocks, and no missed accepted sample in the detection lane;
- headroom: publish post-route LUT, FF, LUTRAM, BRAM, and DSP use. The initial
  acceptance budget leaves at least 15% of each resource class unused; any
  exception is reviewed before a radio boot and is never hidden by changing a
  threshold, clock, or test vector;
- RX correctness: under deterministic replay/injection, full-rate DMA hashes
  match a detector-disabled control; in every test, timestamps remain monotonic,
  no unexplained gaps or overflow occur, and x2/x4 lane phase plus delay maps
  exactly to the full-rate index;
- RX-only attestation: only RX voltage channels 0 and 1 are scan-capable, no
  TX DMA/DDS IIO device is live, every exactly inventoried TX hardware-gain
  control is <= -80 dB, the one shared AD936x TX-LO control is powered down,
  and removed-device DT markers match the image. The receipt must not invent a
  second LO or a second 1R1T gain control that the IIO ABI does not expose;
- identity and rollback: exact serial and USB-topology lock, exact `/32` route,
  isolated known-host file, pre/post receipts, new boot ID, unchanged
  persistent QSPI/Linux hash, bounded cleanup, automatic rollback, and proof
  that the prior persistent image and radio target are restored; and
- claims: evidence is labeled `synthetic`, `replay`, `radio-transport`, or
  `live-signal`. Passing capture plumbing without an observable signal does
  not become a PSS-detection claim.

## Sequential, testable stage gates

### Gate 0: PPU foundation on `main`

- Merge generic target-aware setup and receipt support into PPU `main` through
  its normal review and CI process.
- Add a versioned RX-only RAM attestation/receipt path without changing legacy
  2R2T receipt behavior. Test schema dispatch, exact target readback, missing
  TX-device expectations, safe-state proof, identity locking, and rollback.
- Do not begin a target-radio RAM boot until the PPU version used by the trial
  is merged, pinned, and capable of producing a sealed receipt.

Pass artifact: PPU `main` commit, green CI, target-profile tests, and an offline
receipt/recovery fixture. Starlink code is not part of this commit.

### Gate 1: frozen oracle and 15 MS/s offline acquisition

- Freeze native and edge-projected templates, CI16 quantization, capture hashes,
  CFO grid, tie rules, cadence rules, and expected output for the real replay.
- Reproduce the known 750 Hz lattice and robust exact-template peaks; run
  time-shifted, wrong-template, noise-only, and unrelated-capture controls.
- Predeclare event matching tolerance, minimum multi-frame confirmation, and
  false-alarm ceiling before evaluating held-out data.
- Preserve the lag-monitor analysis and its expected no-event result at 0.75.

Pass artifact: a machine-readable replay report with provenance, matched and
missed frames, timing error, score distribution, and negative-control rate.

### Gate 2: 15 MS/s FPGA tracking and RX-only implementation

- First integrate and validate the AXI diagnostic monitor without calling it a
  detector. Then implement the one-bank, 65-lag raw-result exact correlator at
  100 MHz. Prove the captured samples, stored raw timestamps, coefficient-bank
  identity, 48-bit accumulators, and all 65 score tuples before adding a winner
  reducer.
- Add the exact rational reducer, one-lag nine-bank CFO-refinement mode,
  commanded adjacent-bank validation, double-buffered result publication, and
  single-shot trace. Per-frame CFO switching is forbidden in normal tracking.
- Prove bit-exact equivalence in simulation on structural vectors and bounded
  real-capture windows, including all 210 frozen replay windows, ties,
  enable/gap/index-jump flushing, coefficient rejection, and publication
  overrun accounting.
- Run OOC reports, then full RX-only shell implementation and every common
  timing, DRC, resource-headroom, DMA-equivalence, and device-tree gate.
- If the exact engine misses its budget, reduce parallelism or scheduling while
  preserving numerical behavior. Do not weaken oracle agreement.

Pass artifact: routed bitstream reports plus a replay/simulation equivalence
bundle at the exact source commits.

### Gate 3: target-radio 15 MS/s RAM qualification

- Recheck for an existing IIO/USB owner before mutation. Stop rather than
  evicting an unrelated process or touching another radio.
- Qualify `ad9363a-1r1t` first, because 15 MS/s fits its documented 20 MHz
  analog-bandwidth class. Repeat transport and safe-state qualification with
  `ad9361-1r1t` without changing the FPGA detector geometry.
- RAM boot only. Run detector-disabled and detector-enabled capture pairs,
  verify full-rate DMA equivalence, exercise AXI status, and bound the live
  observation window. Roll back after each target profile.
- A controlled replay/injection can qualify the complete detector path. An
  ambient trial with no signal qualifies transport and rollback only.

Pass artifact: sealed receipts for both target profiles, capture/status hashes,
timing and continuity metrics, and rollback proof. A `live-signal` claim also
requires multi-frame exact-template agreement with the oracle.

### Gate 4: 30 MS/s full-rate DMA plus x2 detection lane

- Start only after the complete 15 MS/s evidence bundle is reviewed.
- Preserve 30 MS/s DMA and qualify a deterministic x2 detection lane against
  the versioned 15 MS/s oracle, including anti-alias response and timestamp
  phase/delay mapping.
- Before freezing that architecture, compare it with a bounded sparse
  native-30-MS/s correlator using the already frozen 132-sample template. The
  chosen path must win on generated resource/timing reports and exact replay
  equivalence, not on an estimate.
- Use `ad9361-1r1t` for full intended bandwidth; an AD9363A run is explicitly
  labeled bandwidth-limited and cannot qualify full-band 30 MS/s reception.
- Repeat all offline, implementation, safe-state, capture-continuity, live,
  and rollback gates. No synthetic-only result is hardware qualification.

Pass artifact: x2 lane equivalence, routed 30 MS/s reports, exact-radio receipt,
full-rate capture evidence, and rollback proof.

### Gate 5: 60 MS/s full-rate DMA plus x4 detection lane

- Start only after 30 MS/s closes. Require `ad9361-1r1t`, an achieved and
  recorded sample clock, and measured analog filter settings.
- Preserve 60 MS/s DMA into DDR and qualify a deterministic x4 detection lane
  exactly as at x2. Re-run all timing/resource checks at the achieved clocks
  and stress DDR/USB backpressure, overflow reporting, thermal behavior, and
  long-run timestamp continuity. Use bounded DDR captures or segmented readout;
  do not imply that USB can continuously carry the raw full-rate stream.
- Re-evaluate the x4 DDC against bounded sparse native-rate correlation after
  30 MS/s results are known. The x4 filter has a different quantized response
  and therefore requires a new versioned template digest; it cannot inherit the
  direct-15-MS/s template identity merely because its output rate is 15 MS/s.
- The AD9361 nominal 56 MHz analog RF bandwidth is not described as a flat
  60 MHz passband. If the practical clock is 61.44 MS/s, version that exact
  geometry rather than labeling it 60. If RF response, timing, or transport
  fails, retain the evidence and stop; do not reinterpret a narrower capture
  as full-rate qualification.

Pass artifact: x4 lane equivalence, routed achieved-clock reports, exact-radio
receipt, sustained detector/DMA-ingress metrics, bounded capture evidence,
RF-response record, and rollback.

### Gate 6: SSS, only after each PSS rate closes

- Freeze an SSS oracle and test vectors only for a rate with qualified PSS
  timing, CFO, sideband, cadence, and false-alarm behavior.
- Demonstrate host SSS recovery from PSS-gated windows before budgeting FPGA
  logic. Report timing evidence separately from decoded identity/content.
- Any FPGA SSS block receives its own functional, resource, timing, radio, and
  rollback gates; it does not inherit qualification merely from PSS.

## Stop rules and evidence ledger

Every build and trial records parent/submodule commits, tool versions, waveform
digests, rate and decimator geometry, Vivado reports, image hashes, PPU commit,
target and sealed receipt, radio serial/topology, live RF/IIO attestation,
capture hashes, detector configuration, result metrics, rollback proof, and
the evidence label.

Stop immediately on identity drift, route contention, an unexpected owner, a
live TX device, unexpected scan channels, source-lock mismatch, negative timing
or hold slack, a critical DRC, resource-budget breach, DMA gap/overflow,
timestamp-map disagreement, oracle disagreement, or missing rollback evidence.
No stage is skipped because a later rate happens to synthesize, and no failed
gate is converted into a pass by changing terminology or lowering a threshold.
