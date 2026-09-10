# Direct 66-tap coarse alternative — isolated experiment, DO NOT MERGE

The direct alternative is **not bit-identical to the current coarse detector**
and does not pass the predeclared numerical comparison gate on all controls.
It is not selected for receiver integration. Both the numerical failure and
the physical failure below are retained as evidence; no production test,
coefficient, clock constraint, detector, or pilot path was changed.

Sources start at firmware `ec36b96965df76f83b80e70c1aba867e7cbbbc30` and HDL
`eb96c64738697c10b9c0abb379ab64f6a4a5c59c` in independent worktrees on
`codex/starlink-rx-only-do-not-merge-direct-coarse`. The first arithmetic slice
is HDL `6414d7d0`; firmware `2bb5a3da2` records the initial numerical experiment.
The subsequent source commits and artifact hashes are recorded in the branch
history and evidence manifest. This is an offline numerical/cycle experiment
and a small arithmetic RTL slice, not a receiver implementation.

## Numerical contract and findings

The candidate uses the original 66 Q1.15 complex coefficients and exact
`sum(x * conj(h))`, with no tap-product rounding. This is the existing
`starlink-fixed-correlator-v1` arithmetic. Legal 66-tap CI16 inputs cannot
reach its signed-48 saturation rail. Its exact rational, ties-to-even unsigned
eight-bit normalized score is a separate contract from the current coarse
18-bit forward FFT / Q17 spectrum product / inverse FFT with block floating
point scaling. The candidate does not round direct accumulators into a
pretend BFP result.

The checked coefficient path is projected 15 MS/s PSS, Q15 quantization,
conjugate reversal, 512-point Xilinx template FFT with fixed /4 scaling, and
Q17 output. The same provenance check includes the original source-30 x2-DDC
and source-60 x4-DDC conditioned templates, both still 66 canonical taps.
Upper-edge regenerated ROMs exactly match all three tracked Q17 memories.
Lower-edge banks were regenerated from the existing oracle and are separately
identified in the JSON; this is not a qualification of lower-edge hardware
switching or source-rate DDC processing.

Taking the ideal inverse transform of each quantized frequency-domain kernel
recovers a 512-sample impulse response, not a finite 66-sample response. All
446 nominal tail samples are nonzero above 1e-15 for each bank. For upper15:

| Quantity | Measured value |
|---|---:|
| Tail energy / total energy | 4.5409867302e-9, or −83.428498 dB |
| Maximum tail magnitude in Q15 units | 0.355620950 |
| Relative total impulse L2 error against original Q15 taps | 7.4827813e-5 |
| Exact Q15 coefficient energy | 1073742825 |

The tail alone is not a bound on the complete FFT/BFP chain's error. BFP
scaling depends on all 512 samples, so a large sample outside one candidate's
66-sample support can also change its quantization error.

Before evaluation, the comparison gates were fixed at maximum absolute score
difference <=1 LSB and exactly equal global peak index. These are comparative
gates, not detector sensitivity or lock criteria. Every beyond-tolerance
score is retained in the JSON; failures do not change the gates.

The existing frozen 1,341-score fixture is read only from the parent worktree's
`input-cursor-paired-v1/frozen_sources`. The unchanged current 18-bit Xilinx C
model reproduces every frozen score and both exponent lists exactly. The
direct alternative changes six scores by one LSB, with the same global peak.
Its complete direct integer stream also matches the independent existing
saturating direct oracle on that fixture.

Initial 98 controls cover upper/lower, integer starts 0/447/959, residual CFO
−1.2 MHz/−100 kHz/0/+100 kHz/+1.2 MHz, mean per-PSS-sample SNR −12/0/12 dB,
noise only, zeros, clipped signal, and signed endpoints. Both float and current
FFT comparisons meet the declared gates on these controls. Peak equality does
not mean the peak is at the injected origin or that a PSS was detected,
especially at the wide CFOs and low SNRs. Scores at each known origin are
retained for that reason.

Four added dynamic-range controls preserve all original 98 input digests:
an isolated complex full-scale impulse and near-one-LSB noise with that
impulse at index 400, on both edges. The latter **fails** comparison to the
current FFT chain:

| Edge | Changed scores | Differences >1 LSB | Maximum difference | FFT / direct global peak |
|---|---:|---:|---:|---:|
| Upper | 369 | 105 | 9 LSB | 270 / 662 |
| Lower | 414 | 138 | 9 LSB | 244 / 1202 |

Direct and independent float scores match exactly on those two controls.
These are differing maxima of a noise/interference control, not PSS detection
or false-alarm-rate measurements. Overall, 2/102 cases fail the FFT comparison;
0/102 fail the float comparison, whose maximum score difference is one LSB.
This evidence rules out substituting the candidate under the original
numerical contract without a separately reviewed acceptance decision.

## Implemented arithmetic and measured resource cost

The isolated `starlink_pss_direct_mac6.v` accepts six CI16 samples and six CI16
coefficients per issue beat, with first/last markers and a stored 64-bit raw
first-tap timestamp plus 32-bit epoch. Eleven consecutive accepted beats form
one result. Three products per lane use exact 16x16, 16x16, and 17x17 signed
multiplication. The Gauss pre-add is 17 bits (`xi+xq`), as is `hi-hq`; truncating
either to 16 bits fails signed-endpoint cases. Products have 32/32/34 bits,
post-adds 35 bits, and accumulators/reduction are 40 bits. Even the generic
66-tap bound `66*2^31 < 2^38` fits; folding/reordering cannot change a reachable
saturation event because none exists in this legal domain.

Operand, product, and complete-tap registers feed six partial accumulators;
the last beat copies final partials into a six-to-three-to-two-to-one registered
reduction. Reduction overlaps the next job. Full output stalls hold the entire
pipeline and deassert issue-ready. Synchronous reset/flush discards valid
ownership while stale data registers remain invalid. The RTL test checks 119
completed jobs against an independent four-product integer calculation,
49 exact 11-clock cadence intervals, 168 held-output stall checks, input
bubbles, timestamp wrap, epoch changes, two partial-job aborts, and flushing
an already complete unconsumed tuple. It does not validate malformed job
framing or implement an ADC-ready interface.

Vivado 2022.2 `xc7z010clg400-1`, maximum two threads, actual isolated placement
and route at 200 MHz:

| Slice revision | LUT | FF | Slices | DSP | BRAM tiles | Setup WNS | Hold WHS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Automatic DSP post-add absorption | 1895 | 2244 | 645 | 24 | 0 | +0.543 ns | −0.713 ns |
| Explicit fabric post-adds | 2087 | 2442 | 690 | 18 | 0 | +0.453 ns | −0.713 ns |

Both have eight unique control sets and zero methodology violations and
nonzero check-timing categories. Both physical gates **fail**. The worst hold
path starts at an OOC input timestamp port; the explicit input/output delays
remain unchanged. A positive setup margin does not qualify hold, full receiver
placement, CDC, or board I/O.

The first result demonstrates why three multiplication operators did not imply
three physical DSPs: Vivado duplicated each `m0` when absorbing the real-tap
post-add, generating four DSPs per lane. Explicit fabric post-adds removed six
DSPs but added 192 LUTs, 198 FFs and 45 slices. Both results are retained.

For context, the parent's read-only audit of the best complete receiver shows
the existing service at 1490 LUT/3571 FF/17 DSP/6.5 BRAM tiles and the entire
IQ-to-score path at 3674 LUT/6329 FF/27 DSP/15.5 BRAM. This direct slice alone
already needs 2087 LUT, before the omitted work below. Cross-hierarchy LUT
combining prevents subtracting and summing hierarchy rows into an exact
replacement estimate. A net slice/resource win is not demonstrated.

## Scheduling, ports and omitted engine work

`66*15M = 990M` complex tap-accumulations/s is an operation rate. A simple
six-lane scheduler needs 11 issue clocks/result: 18.18M/s at 200 MHz and
15.91M/s at 175 MHz. Five lanes need 14 clocks and supply only 14.29M/s at
200 MHz. Eleven lanes at 100 MHz need six clocks/result and supply 16.67M/s,
with a corresponding 33-multiplier-DSP hypothesis. Seven lanes at 150 MHz
need ten clocks/result and have no average service headroom. Eight lanes at
150 MHz need nine clocks/result (including six unused tap slots), nominally
16.67M/s before admission/stall costs, with 24 multiplier-DSP candidates.
Trading DSP headroom for a simpler lower-clock implementation may be useful,
but its complete source/memory/normalization budget still decides feasibility.
None of these other clock/lane configurations is synthesized by this experiment.

The executable event model assumes regularly paced 15 MS/s canonical input,
ordered jobs, and overlap of reduction with issue. Six replicated 128x32
simple-dual-port sample memories provide one read per lane and one broadcast
write per source arrival: six logical read ports, six write ports, and six
RAMB18 blocks (three physical BRAM tiles) if each replica uses a 32-bit
simple-dual-port configuration. This is an architectural estimate, not RAM
inference evidence. All 66 taps must be present before a job starts; the model
avoids same-cycle newest-sample read/write and conservatively keeps the whole
window live until its last issue. Banking with a six-way rotation might save
replication but introduces address/mux/control costs not implemented here.

Each lane also needs one 32-bit coefficient read every issue clock. Eleven
words per lane provide one bank; upper/lower need 22 words/lane, or 4224 bits
total. Retaining all source-15/30/60 upper/lower banks needs 12672 bits plus
bank selection and atomic commit. Runtime coefficient inputs in the measured
slice include none of this storage.

The 1.8M-arrival (120 ms) event test at 200 MHz with 200 stalled clocks per
100 jobs has maximum 15-sample backlog, maximum 212-clock issue delay, and no
128-depth history expiry. The same stress with 400 stalled clocks per 100 jobs
has an average rate deficit and expires jobs; five lanes also expire jobs.
These tests prove the model's conditional budget, not sustained acceptance in
an integrated source-clock RTL engine. Arbitrary ADC stalls cannot be hidden
by the slice's issue-ready interface. A real owner must count an overrun or
expiry, abort invalid work, and invalidate affected map windows.

The following costs and contracts remain outside the measured slice:

- Sample history, raw timestamp/epoch retention, input CDC/pacer, six addresses
  per issue, job FIFO/ownership and the demonstrated expiry rule. A separate
  128x96 timestamp/epoch history is 12288 logical bits before physical packing.
  Preserve first-tap timestamps; do not reconstruct them from service latency.
- Exact sliding `Ex=sum(I^2+Q^2)` over 66 samples. The current cache uses two
  square multipliers and retains 38-bit energies; its qualified behavior can
  be reused but has a real LUT/BRAM/DSP cost. `Eh` is cached separately for each
  selected Q15 bank and never copied from the upper15 constant for another bank.
- Exact power and normalization. The current score-preparation block accepts
  an 18-bit BFP mantissa and exponents; it cannot accept a 40-bit direct sum
  unchanged. Legal unit-energy banks bound the correlation to signed 35 bits,
  but a wide exact square still requires extra DSP/LUT arithmetic or a measured
  time-sharing design. The 38x31 energy product, up-to-69-bit comparison ratio,
  ties-to-even 8-bit division, zero-energy behavior, and tagged output FIFO all
  remain necessary. No unmeasured DSP count is credited for these operations.
- Visit fencing, reset acknowledgement, coefficient-bank commit, gap/index
  validation, malformed-job rejection, stalled-output expiry, and ordered map
  publication. The slice's tested flush is only the local arithmetic primitive.

Both FPGA coarse/fine stages and independent 2.5 MS/s IIO GLRT export remain
required. No radio was accessed, no PPU code changed, and no receiver build,
deployment, merge, or push was attempted. Held-out real recordings, phase-map
cadence/sensitivity, original full-rate fine timing, all source rates/edges,
full-image physical closure, .18-before-Ethernet-.17, and the eight-target
120 ms / 300 s scanner remain open.

## Reproduction and evidence

From firmware root, run the Python in PPU's existing virtual environment:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q tests/starlink_oracle/test_direct_coarse_study.py
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python tools/starlink_direct_coarse_study.py --output hdl/library/starlink_pss_direct_coarse/build/reproduction
```

The study command succeeds when it completes the experiment and writes its
results, even when the explicitly reported comparison gate fails. It requires
the hash-checked installed Xilinx C model and the immutable frozen-vector path;
it neither regenerates nor edits the frozen goldens.

From `hdl/library/starlink_pss_direct_coarse`, run Icarus with the two local
Verilog files. For physical evidence, invoke `synthesize_slice.tcl` from a
unique output directory with the supplied `slice.xdc` and the Vivado 2022.2
compatibility library path. The physical script intentionally returns failure
for the measured hold violation.

Tracked evidence under `hdl/library/starlink_pss_direct_coarse/evidence/`
retains initial/extended numerical JSON, both full physical report sets and
transcripts, test receipts and SHA-256 manifests. Large DCPs and proprietary
C-model libraries stay in ignored `build/` directories. These artifacts are
bounded experimental evidence, not clean-source release qualification.
