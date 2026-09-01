# Experimental Starlink PSS repeated-delay detector

This directory is an RX-only, standalone feasibility slice for the protected
`codex/starlink-rx-only-do-not-merge` branch. It has no transmitter interface,
does not modify the Pluto HDL submodule, and is not wired into a firmware image.
A candidate from this block is only a cheap structural hint; it is not evidence
of a Starlink signal and must be followed by exact PSS correlation.

## One core, three exact rates

`starlink_pss_delay_candidate.v` selects one closed geometry at elaboration:

| `RATE_MSPS` | Useful | Inverted CP | Symbol | Repeat delay `D` | Correlation pairs `W=S-D` |
|---:|---:|---:|---:|---:|---:|
| 15 | 64 | 2 | 66 | 8 | 58 |
| 30 | 128 | 4 | 132 | 16 | 116 |
| 60 | 256 | 8 | 264 | 32 | 232 |

These values match the fixed numerology in `tests/starlink_oracle`. There are
not three copies of the RTL. A later AXI wrapper may turn the compile-time mode
into a reset-only selector; changing geometry in the middle of a stream is
deliberately outside this first slice.

## Metric and threshold

For every contiguous valid CI16 sample, the core forms

```
p[n] = x[n] * conj(x[n-D])
P    = sum(p[n]) over W pairs
E0   = sum(|x[n]|^2) over the current side
E1   = sum(|x[n-D]|^2) over the delayed side
M    = |P|^2 / (E0 * E1)
```

The event test is exact cross multiplication in Q1.15:

```
|P|^2 * 32768 >= E0 * E1 * THRESHOLD_Q15
```

The default `THRESHOLD_Q15=24576` means `M >= 0.75`. Both energy sums must also
meet `MIN_WINDOW_ENERGY`; its conservative default of one rejects a zero-input
window but intentionally leaves the ADC-scale noise-floor policy to later
integration. The output metric is the exact fraction
`candidate_metric_num/candidate_metric_den`, where the numerator is `|P|^2`
and the denominator is `E0*E1`. This avoids a hardware divider and lets host or
later RTL reproduce the comparison without ambiguity.

The inverted PSS prefix contributes a small number of anti-correlated pairs.
It is included in `W` rather than silently treating the prefix as normal CP.
The structural testbench models that rule.

## Arithmetic widths

| Quantity | Width | Reason |
|---|---:|---|
| CI input | signed 16 | Native RX sample contract |
| One real/imag complex product | signed 33 | Sum/difference of two signed 16x16 products |
| One complex-sample energy | unsigned 32 | Two squared signed CI16 components |
| Correlation and energy sums | 41 | Covers the largest 232-pair mode with headroom |
| `|P|^2` | unsigned 83 | Sum of two 41x41 squares |
| `E0*E1` | unsigned 82 | Product of two unsigned 41-bit sums |
| Q1.15 threshold sides | unsigned 98 | Lossless cross multiplication |

All additions, sign extensions, and multiplier outputs are explicitly sized.
No saturation occurs inside the declared 15/30/60 geometries.

## Event timing and stream boundaries

The sliding sum snapshots its first score when the final sample of one complete
symbol is accepted. Wide squaring/energy products and threshold comparison are
split across two further registered cycles, so `candidate_valid` appears two
sample clocks after that final input beat. `candidate_sample_index` travels
through the pipeline and is the accepted final sample index minus `S-1`, so it
names the inferred PSS symbol start (modulo 2^64), not the later output cycle.
The pipeline accepts one new window per clock. The detector emits once per
above-threshold excursion and rearms only after a below-threshold window or a
stream flush. The sample-index and metric buses are valid only with
`candidate_valid`; they otherwise retain the last event until reset.

Any cycle with `in_valid=0`, and any non-consecutive `in_sample_index`, flushes
the delay and correlation history and cancels in-flight metric results. The
current sample after an index jump is retained only as the first sample of a
fresh history. Reset is asynchronous, active low, zeros all externally valid
outputs, and invalidates all history. Memory bits are not reset because count
gating requires every entry to be overwritten before it can affect a score.

## Focused simulation

Icarus Verilog runs the same RTL and self-checking scenario at all three rates:

```sh
bash hdl-starlink/run_tests.sh
```

Each run covers zero energy, deterministic noise, a strong wrong-period
waveform, an invalid-beat gap, a sample-index jump, an inverted-prefix positive
symbol with an exact start-index assertion, and no pulse storm during a
continued coherent run. The launcher also asserts that an unsupported rate is
rejected at time zero rather than silently mapped onto one of these geometries.

The simulation results above make no Vivado synthesis, timing, utilization,
hardware integration, or radio-deployment claim.

## Preliminary standalone synthesis measurement

The exact committed core was also measured with Vivado 2022.2 build 3671981,
`synth_design -mode out_of_context`, and part `xc7z010clg400-1`. The constraint
was 16.666 ns for every mode so that all three elaborations were checked against
the eventual 60 MS/s clock, not relaxed according to their input rate.

| Mode | Total LUT | Logic LUT | LUTRAM | FF | BRAM | DSP48E1 | Synth WNS at 16.666 ns |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 1,597 | 1,163 | 434 | 907 | 0 | 21 | +3.523 ns |
| 30 | 1,878 | 1,314 | 564 | 921 | 0 | 21 | +3.523 ns |
| 60 | 2,001 | 1,307 | 694 | 915 | 0 | 21 | +3.523 ns |

These are measured post-synthesis estimates, not placed/routed results. The OOC
clock lacks top-level clock-location, input-delay, output-delay, congestion, and
integration context. Positive synth WNS therefore proves neither 60 MS/s route
closure nor firmware fit. `synth_ooc.tcl` reproduces the measurement into an
absent output directory, for example:

```sh
vivado -mode batch -source hdl-starlink/synth_ooc.tcl \
  -tclargs hdl-starlink/starlink_pss_delay_candidate.v 60 /tmp/pss-ooc-60
```

The 21-DSP result is the main integration risk. Six DSP multipliers implement
the streaming CI16 complex product and sample energy; the three exact 41x41
metric products expand into the remaining 15. The default constant Q1.15
threshold is optimized as constant arithmetic, but its 98-bit compare remains
wide. Before integration, compare this exact reference against a first-stage
block-floating or truncated metric, a shift/add magnitude-energy gate, and a
candidate-gated/time-multiplexed exact score. Any replacement must retain these
tests and be checked against the golden oracle before claiming equivalent
detection behavior.
