# Starlink PSS 15/30/60 MS/s RX-only development plan

Status: experimental, RAM-only, and **DO NOT MERGE INTO FIRMWARE MAIN**.

Target radio: `104000bac4950008230026001b440a003a` only. A USB address, serial
TTY, network interface, or `usb:B.D.I` URI is never accepted as identity by
itself; each hardware operation must re-resolve and lock the serial plus USB
topology immediately before use.

## Stable boundary between PPU and firmware

PPU remains generic product tooling and is developed through ordinary reviewed
pull requests into PPU `main`. Its responsibility is to model, plan, attest,
and receipt explicit AD936x driver/channel targets:

- `ad9361-2r2t`: legacy/default Pluto+ behavior;
- `ad9363a-1r1t`: native constrained driver and one digital RX stream;
- `ad9361-1r1t`: wider AD9361 driver limits with one digital RX stream.

These names attest the live Linux driver profile and stream geometry, not the
physical RFIC die marking. No PPU code is Starlink-specific.

All waveform, detector, RX-only HDL/Linux, build, and radio-trial changes stay
on `codex/starlink-rx-only-do-not-merge` and its identically marked submodule
branches. They are never merged to firmware `main`.

## Fixed geometry and performance target

The native waveform is 240 MS/s, 1024 useful samples, 32 samples of inverted
prefix, and a 750 Hz frame rate. Exact integer projections are:

| Rate | Useful | Prefix | Symbol | Frame | Repeat delay |
|---:|---:|---:|---:|---:|---:|
| 15 MS/s | 64 | 2 | 66 | 20,000 | 8 |
| 30 MS/s | 128 | 4 | 132 | 40,000 | 16 |
| 60 MS/s | 256 | 8 | 264 | 80,000 | 32 |

One sample is accepted per RX clock. A structural candidate can therefore be
available after one 4.4 us PSS symbol plus pipeline latency. Acquisition still
waits up to one 1.333 ms frame; four-frame confirmation is about 5.33 ms and
eight-frame confirmation about 10.67 ms.

## Detector architecture

1. Tap formatted RX0 I/Q before the optional capture decimator. Keep the
   existing RX timestamp and DMA behavior independent.
2. A streaming repeated-delay detector uses the compile-time geometry above to
   find cheap PSS-like candidates. A candidate is only a hint.
3. Freeze the candidate index and a bounded surrounding window. Verify it
   against the exact lower/upper PSS templates and explicit CFO hypotheses,
   initially with the host golden oracle and later with a candidate-gated,
   time-multiplexed FPGA MAC if resources justify it.
4. Confirm the 750 Hz repetition across multiple frames before reporting frame
   alignment. Do not call a single correlation peak a Starlink detection.
5. Gate SSS work until PSS timing, rate, sideband, CFO convention, and
   false-alarm behavior are closed at the current rate.

The first RTL deliberately preserves exact wide arithmetic as a measurement
reference. Vivado out-of-context results decide whether it is integrated as-is
or replaced by a narrow shift/add screening metric followed by candidate-gated
exact scoring. Timing or resource failure is design evidence, not permission to
relax numerical tests silently.

The committed exact core currently measures as follows with Vivado 2022.2
post-synthesis OOC at a common 16.666 ns constraint. These are not routed or
integrated results:

| Rate | LUT | FF | LUTRAM | DSP48E1 | Synth WNS |
|---:|---:|---:|---:|---:|---:|
| 15 | 1,597 | 907 | 434 | 21 | +3.523 ns |
| 30 | 1,878 | 921 | 564 | 21 | +3.523 ns |
| 60 | 2,001 | 915 | 694 | 21 | +3.523 ns |

## RX-only shell

The experimental shell compiles `MODE_1R1T=1`, disables the AD936x FPGA DAC
datapath and TDD logic, removes TX DMA/packer/interpolation, removes tandem AGC,
removes the second PS high-performance port, and holds the digital TX pins
static. Linux disables the absent TX DMA/DDS/TDD/tandem devices, selects 1R1T,
and skips TX digital-interface tuning.

Before a radio trial, prove all of the following from the running image:

- only RX voltage channels 0 and 1 are scan-capable;
- no TX DMA/DDS IIO device is live;
- the RFIC transmit path is muted/powered down by the existing boot-safety
  mechanism, independent of constant FPGA samples;
- RX DMA metadata, counter continuity, overflow reporting, and ordinary IIO
  capture still behave as before.

## Sequential gates

### Gate 0: immutable oracle and offline replay

- Frozen provenance and SHA-256 for native and both edge projections.
- Float and CI16 fixed-point agreement on exact lag and deterministic ties.
- Overflow, saturation, zero-energy, wrong-period, gap, and index-jump tests.
- Real 15 MS/s replay is provenance-bound; 30/60 remain labeled synthetic
  until exact-radio captures exist.

### Gate 1: implementation closure

- Icarus passes the same testbench at 15/30/60.
- Vivado 2022.2 out-of-context synthesis reports utilization and timing for
  each rate; no estimate is substituted for a report.
- Full Zynq-7010 implementation has non-negative setup/hold slack and leaves
  practical LUT/FF/DSP/BRAM headroom for the AXI/status integration.
- Device tree compiles and contains disabled nodes for every removed block.

### Gate 2: 15 MS/s RAM trial

- Use `ad9363a-1r1t` first when its 20 MHz analog bandwidth is sufficient;
  cross-check with `ad9361-1r1t` without changing the FPGA geometry.
- RAM boot only, exact serial lock, exact `/32` route, known-host isolation,
  pre/post receipts, automatic rollback, and persistent-image verification.
- Pass deterministic injected/replay vectors, then a bounded live RX trial.
- Require correct index within the declared tolerance, multi-frame cadence,
  zero DMA gaps/overflows, and a predeclared false-candidate ceiling.

### Gate 3: 30 MS/s

- Start only after the 15 MS/s evidence bundle is complete.
- Rebuild with 30 MS/s geometry; do not change rate live mid-stream.
- Use `ad9361-1r1t` when the native AD9363A bandwidth limit clips the capture.
- Repeat every offline, implementation, rollback, capture-continuity, timing,
  cadence, and false-alarm gate. A synthetic-only result is not hardware
  qualification.

### Gate 4: 60 MS/s

- Start only after 30 MS/s closes.
- Require `ad9361-1r1t`, an achieved 60 MS/s (or an explicitly recorded exact
  clock rate), and measured analog bandwidth; the AD9361 nominal 56 MHz RF
  bandwidth is not described as a flat 60 MHz passband.
- Repeat the complete gate set, with special attention to RX clock timing,
  DMA continuity, USB/DDR backpressure, and thermal/power stability.
- If timing or RF bandwidth fails, preserve the result and evaluate a 61.44
  MS/s native-clock geometry or channelized detector as a new reviewed scope.

## Evidence and stop rules

Every build records parent/submodule commits, tool versions, waveform digests,
rate geometry, Vivado reports, packed-image hashes, PPU target and receipt,
radio serial/topology, live RF/IIO attestation, capture hashes, detector
configuration, result metrics, rollback proof, and whether evidence is
synthetic, replayed, or live.

Stop immediately on identity drift, route contention, a live TX device,
unexpected scan channels, source-lock mismatch, negative timing slack, DMA
gaps/overflow, missing rollback evidence, or a detector/oracle disagreement.
No stage is skipped because a later rate happens to build.
