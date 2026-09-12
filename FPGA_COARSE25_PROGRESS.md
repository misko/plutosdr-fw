# Coarse25 continuation checkpoint — 2026-09-12 06:19 UTC

**Latest decision checkpoint:** [timebox review; not deployed](FPGA_COARSE25_TIMEBOX_REVIEW.md).
**Earlier checkpoint:** [complete detector RTL and routing](FPGA_COARSE25_DETECTOR_CHECKPOINT.md).
The following preserves the earlier arithmetic-only milestone.

Goal unchanged: **2.5 / 5 / 15 MS/s FPGA PSS detection, with a 2.5 MS/s
inspection stream enabling independent host GLRT verification.** Not complete
and not deployed. The previous goal turn made progress by finding the failed
screen; this turn made progress by identifying a useful band-centering path,
validating it against blind GLRT, and implementing/routing the first MAC.

The original 05:32–13:32 UTC eight-hour feasibility budget is not extended.
The original failed screen and all intermediate failures remain preserved.

## What changed our next action

1. Normalizing local input energy, as the existing wider-band PSS oracle does,
   did **not** remove the wrong-epoch peak in the original 2.5 MS/s stream.
2. Widening CFO search from +/-400 to +/-800 kHz did **not** rescue that
   already-filtered narrow stream either.
3. Wider-band development controls at 5 and 15 MS/s did find the pilot epoch
   in both 120 ms windows, selecting the +500 kHz hypothesis:

| Rate | 36.5 s peak z / phase difference | 37.0 s peak z / phase difference |
| --- | --- | --- |
| 5 MS/s | 18.94 / 0.067 us | 24.06 / 0.133 us |
| 15 MS/s | 32.96 / 0.000 us | 35.96 / 0.133 us |

These use a wider CFO search and different rate-specific templates than the
failed screen. They are development diagnostics, not a retrospective pass of
that screen or verification of a deployed 5/15 MS/s detector. The new 5 MS/s
filter remains an unqualified experimental response.

4. Centering **before** the 15 -> 2.5 MS/s filter using the earlier pilot
   alternative +512585.3848550797 Hz recovered useful narrow PSS:
   z 9.689 / 13.540, with 0.067 / 0.200 us disagreement from saved pilot epochs.
   The earlier +285941.79442491336 Hz alternative did not pass both windows.
   Both alternatives are recorded in the earlier 36.0/36.1/36.2 s pilot receipt.
   The useful alternative was not that receipt's majority-supported selection;
   a live policy must retain/resolve aliases rather than silently assume it.

This demonstrates a workable **frequency-centered** narrow-band development
path. It does not prove blind 2.5 MS/s acquisition at arbitrary LNB offset,
an absolute CFO calibration, or absolute timing accuracy.

## Separate temporal validation on exactly the same exported IQ

The subsequent 120 ms windows were frozen before this evaluation: 36.62 s,
37.12 s, and negative controls at 1.12 s and 1.62 s. They do not overlap the
new detector's first 120 ms development windows. They remain within a known
episode previously covered by wider-band studies, **not independent captures**.

The predeclared centering uses the earlier +512585.3848550797 Hz alternative.
Each 120 ms CI16 output is written, read back, and supplied to PSS; its first
20 ms independently feeds blind host acquisition and GLRT. No PSS timing/CFO
candidate seeds GLRT and no same-window GLRT result seeds PSS.

| Window | PSS z | Blind GLRT margin | PSS/GLRT phase difference | Frozen gate |
| --- | --- | --- | --- | --- |
| 36.62 s | 11.2708 | 0.56138 | 0.333 us | PASS |
| 37.12 s | 14.1470 | 0.60733 | 0.067 us | PASS |
| 1.12 s | 4.9210 | 0.01165 | Not meaningful below threshold | PASS |
| 1.62 s | 4.7269 | 0.00776 | Not meaningful below threshold | PASS |

Acceptance was PSS z >=8, GLRT margin >=0.025 and positive phase difference
<=2 us; negatives require both below threshold. Negative controls precede the
frequency receipt, so their use of this correction is noncausal and explicitly
not an operational earlier-time acquisition test. Small negative counts do not
qualify false-alarm rates. Real RF absence is not independently established.

Each exported file is 1,200,000 bytes / 300,000 complex samples, with hashes,
first source centers and stride in the receipt. They are local model exports,
**not** IIO transfers or radio captures made during this turn.
All four gates also passed a second complete run.

## Implemented RTL and routing evidence

New `hdl/library/starlink_coarse25/starlink_coarse25_mac.v`:

- Exact 16-tap complex Q15 correlation and input-window energy.
- Registered read, multiply, pair-sum and accumulate stages.
- Output latency 19 calculation clocks; input spacing >=20 clocks. At the
  intended 100 MHz / 2.5 MS/s there are 40 clocks per accepted sample.
- No backpressure output. Reset, index gaps and overloads expire partial work.
- The output timestamp names the first correlation-window sample, not an
  already-corrected PSS epoch. Template/filter coordinate correction remains
  an explicit integration obligation.

**61 focused tests pass**, including four MAC/ROM RTL-contract tests and
independent full-width chronological integer dot products. This is not a
full-repository, whole-FPGA, or radio qualification count.

Routing progression, all preserved:

- First unpipelined MAC: setup -1.915 ns, hold +0.159 ns; fail. Worst path
  crossed history selection, multiplication and wide accumulation in one cycle.
- Pipelined standalone probe: internal setup +0.799 ns, but 98 input ports
  lacked boundary delays; not accepted as a fully constrained probe.
- Explicit standalone input constraints: setup +0.799 ns, hold -0.137 ns;
  unroutable OOC input/partition pins made boundary timing unsuitable.
- **Registered source/MAC/sink harness: setup +1.057 ns, hold +0.131 ns at
  100 MHz; all twelve `check_timing` categories report zero issues.**
  Routed MAC: 464 LUTs, 945 FFs, six DSPs, zero BRAM. Entire harness: 475 LUTs,
  1227 FFs, six DSPs. The OOC clock origin is a declared BUFGCTRL_X0Y0
  assumption; this is still not the clock network of a full receiver.

No normalization divider, phase map, candidate gate, CDC, DMA or actual FFT
was included in this new harness. Do not extrapolate its timing or resources
to the complete receiver. No new shared FFT is intended.

## Next implementation steps, keeping the full goal

1. Add exact fixed-point normalized scoring and compare quantized real-recording
   outcomes with the accepted float reference; do not assume 8-bit scores retain
   sensitivity. Reuse the existing reviewed divider only after verifying its
   width/latency/reset contract in this new pipeline.
2. Add rational 750 Hz phase accumulation, candidate confidence and explicit
   drop/epoch accounting. Budget CFO banks and memory before replication.
   A zero-residual bank now has evidence after centering; full live CFO coverage
   and alias-selection behavior still need qualification.
3. Integrate one accepted 2.5 MS/s stream feeding both detector and independent
   IIO/DMA IQ output. Route the **full board** and verify sample counters, gap
   reports, sustained 10 MB/s CI16 payload, 120 ms and 300 s runs, and restart.
4. Serial-lock and qualify .18 first, then deploy via Ethernet PPU to .17 after
   resolving its changed SSH trust. Scale RX input to 5 then 15 MS/s while
   retaining the verified 2.5 MS/s inspection/detector path and validating each
   rate's actual filtering, calibration and index mapping. Wider-rate direct
   detector diagnostics above are not substitutes for these integration tests.

No radio operations this continuation. The earlier read-only .18 identity
check and .17 SSH pin failure remain the last observations; neither radio
was flashed or reconfigured. No PPU source changes; preexisting dirty PPU files
remain untouched. Firmware and HDL stay on `codex/pss-coarse25-do-not-merge`.

## Evidence

- [Normalized development](reports/coarse25-normalized-development-20260912/result.json)
- [Wider CFO development](reports/coarse25-wide-cfo-development-20260912/result.json)
- [5/15 MS/s controls](reports/pss-five-fifteen-development-20260912/result.json)
- [Earlier majority CFO](reports/coarse25-causal-recenter-development-20260912/result.json)
- [Earlier alternative CFO](reports/coarse25-causal-alias-development-20260912/result.json)
- [Frozen temporal plan](reports/coarse25-temporal-validation-20260912/plan.json)
- [Same-IQ blind GLRT verification](reports/coarse25-temporal-validation-20260912/result.json)
- [All MAC routing probes](reports/coarse25-mac-routing-20260912.tar.gz)
  SHA256 `de98b3feb3c029d61eef88dd9e3775f8cea278ca836fc2ad587ad1bb87c6d486`.

Raw routing directory:
`/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/fresh-coarse25-artifacts.ZwJPCrqH/mac-registered-v1`.
The earlier source versions remain in Git; the original normalization/recenter
diagnostic revision is `1b7386b5f`, and the first unpipelined HDL is `f68b0a832`.
