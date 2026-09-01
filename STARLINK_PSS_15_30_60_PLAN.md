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
   multi-frame 750 Hz cadence. Record the selected sideband, CFO, phase, and
   uncertainty window.
3. Hand only bounded predicted windows to a candidate-gated FPGA exact
   correlator. The first implementation targets 64 trial phases centered on an
   approximately +/-32-sample window, 66 template taps, nine declared CFO
   hypotheses, and 750 windows/s.
   That is about 28.5 million complex MACs/s before implementation overhead,
   suitable for evaluation as a time-multiplexed 100/200 MHz engine rather
   than 66 parallel tap multipliers. This is a workload estimate, not timing
   closure.
4. Compare every FPGA score, selected hypothesis, event index, and timestamp
   against the bit-accurate host oracle. Confirm multiple 750 Hz frames before
   declaring alignment; a single peak is only a candidate.
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

The trusted full-shell run `33540748707` at parent commit `829380e76240` and
HDL source `091f8d5852fa` also completed implementation and produced a fully
routed RX-only checkpoint. It used 4,429/17,600 LUTs (25.16%), 7,173/35,200
registers (20.38%), 3/60 BRAM tiles (5%), and 28/80 DSPs (35%). Routed setup
WNS was +2.049 ns and hold WHS was +0.006 ns, with zero setup and hold failing
endpoints. Both remaining RX timestamp-FIFO bus-skew constraints were met at
+8.997 ns and +9.413 ns. Packaging then stopped because its inherited policy
expected four RX-plus-TX FIFO constraints; the RX-only shell intentionally has
only the two RX crossings. That manifest-specific count has been corrected
without weakening the four-constraint requirement for other builds, but a new
trusted run must pass before this shell becomes RAM-boot eligible.

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
  detector. Then implement the candidate-gated exact correlator and host handoff.
- Prove bit-exact equivalence in simulation on structural vectors and bounded
  real-capture windows, including enable/gap/index-jump flushing.
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
