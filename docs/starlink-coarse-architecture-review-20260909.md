# Coarse acquisition architecture review — no replacement selected

Scope remains both FPGA PSS stages, independent 2.5 MS/s pilot capture, .18
canary then PPU Ethernet .17 verification, and the full 15/30/60 MS/s,
eight-target 120 ms / 300 s scanner. This review authorizes no radio change,
detector removal, different FPGA, narrowed rate requirement or firmware merge.

## Measured problem

The canonical coarse search runs at 15 MS/s at every source rate; 2.5 MS/s is
the separate pilot inspection product, not the existing coarse search rate.
Full-rate samples also feed sparse fine timing. The shared coarse engine moves
forward-transform results back to the 100 MHz template multiplier and then
sends products back to the 200 MHz service for inverse transformation. Each
transform has bank ownership, status/framing validation and actual ACK drain.

The best measured complete receiver (`18c96bb9`) uses 13068/17600 LUTs,
18505/35200 registers, 54/80 DSPs and 53.5/60 BRAM tiles, but all 4400 slices.
100 MHz passes with only +0.019 ns margin; 200 MHz fails at -0.421 ns.
The subsequent metadata-tree experiment improves its targeted path while
worsening whole-receiver WNS to -0.910 ns. Local gate depth is insufficient
evidence of global physical improvement. Unchanged 150/175 MHz variants fail
sustained simulation; deeper buffers alone do not solve a rate deficit.

These results motivate measuring complete engines, including their storage,
normalization, metadata and control costs, rather than comparing FFT cores
alone. No alternative below has been implemented or physically qualified by
this document.

## Bounded options

1. Finish the already-started idle-admission experiment and measure one fresh
   complete receiver. Preserve full current active/final fault checks. Retain
   the best previous checkpoint even if the new experiment is worse.
2. Consolidate FFT, template multiplication, intermediate storage and inverse
   scheduling into one processing block. Measure whether avoiding intermediate
   clock crossings and ACKs outweighs moving more logic into the fast domain.
   Private storage before validated publication already exists; re-proposing
   that alone is not a new architectural saving. Reset/config/event ordering
   still needs independent actual-core checks, not assumed latency bounds.
3. Evaluate a direct time-shared correlator for the 66-sample window. At 15 MS/s
   it requires 990 million complex tap-accumulations/s. This is an operation
   budget, not a DSP count or proof of fit: memory ports, coefficient width,
   accumulator scheduling, normalization, stalls and fault handling all count.
   A direct finite-tap implementation is not automatically bit-identical to
   the existing quantized FFT/BFP chain. In particular, frequency-domain
   coefficient quantization can change the effective impulse response.
   Preserve the existing frozen numerical contract as the reference; any
   different numerical contract needs an explicit version and acceptance
   decision before promotion, not silently relaxed tests.
4. Consider narrower-rate coarse detection only after offline sensitivity,
   residual-CFO coverage and alias/filter tests. Retain negative observations.
   Host-assisted GLRT must precede the assisted observation and meet measured
   control latency; it cannot silently replace independent blind comparison.

## Evidence required before selecting a replacement

- Exact input/reference/filter identities and explicit numerical error budget;
  known timing/CFO/noise/clipping controls and held-out real recordings.
- Continuous 15 MS/s canonical processing with bounded backlog under the
  declared stalls, both coefficient banks, resets, expiry and hop fences.
- Full-engine LUT/register/control-set/BRAM/DSP inventory and measured service
  intervals, including input/output transfers and normalization.
- Fresh full-receiver timing/CDC/board-I/O analysis with both PSS stages and
  pilot DMA retained; no inferred feasibility from an isolated block alone.
- Independent .18 transport/native tests and .17 live GLRT/PSS evidence before
  considering a new architecture deployed or the full goal complete.

The current short-dwell lock policy, frequency assistance, persistent recorder
and 30/60 MS/s hardware gates remain separate open work even after timing closes.
