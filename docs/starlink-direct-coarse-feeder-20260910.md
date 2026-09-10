# Direct coarse feeder/history cost study — DO NOT MERGE

The streaming feeder works in the bounded RTL tests, but the combined
feeder+MAC fails isolated physical timing. It is not eligible to replace the
current coarse detector. The earlier direct-vs-FFT numerical failures remain
unchanged: six one-LSB differences in the frozen 1341-score fixture and two
extended dynamic-range controls with differences up to nine LSBs and different
global noise maxima. No comparison tolerance, production golden, detector,
pilot branch or constraint was changed by this continuation.

This continuation starts from firmware
`84c48b347cc0c7f13f15403eaa174f9076d4fda3` and HDL
`a29d4fc27e2b92311131d07c53fb559bff37c697` in the same independent
`codex/starlink-rx-only-do-not-merge-direct-coarse` worktrees. See the earlier
`starlink-direct-coarse-evaluation-20260910.md` for the numerical contract and
MAC-only experiment. The new evidence is a standalone synchronous feeder,
history store and arithmetic engine, not an ADC/receiver integration.

## Implemented contract

`starlink_pss_direct_feeder.v` has no source-ready output. Every source beat
while `resetn` is asserted is accepted and counted, including a beat coincident
with a fence. Source input is already the canonical 15 MS/s sequence, presented
synchronously to the 200 MHz service clock. The test uses exactly 13,13,14
service clocks between source beats. ADC crossing, canonical conditioning,
arbitrary input bursts and source-clock reset coordination are outside scope.

Canonical ordinals advance by one regardless of the original source rate.
The internal 16-bit ordinal wraps modulo 65536; pointer differences stay
unambiguous because retention expires at 128, well before half-range.
The original 64-bit source timestamps are independent: their declared stride
is 1/2/4 for source15/30/60, respectively. The actual first-tap timestamp is
read from history and carried through the existing MAC, not inferred from the
ordinal or service latency. Source timestamp addition is modulo 2^64. This
engine never resets or drives the external source counter.

Six replicated 128x32 simple-dual-port sample histories provide six reads per
issue clock and one broadcast write per accepted source beat. A separate
128x64 memory retains each raw timestamp. All 66 samples must exist before the
first of eleven six-tap issue groups is read. One synchronous read stage feeds
the tested six-lane MAC. Input writes continue when its output is stalled.
The implementation forbids read/write collision on retained history and
conservatively retains a whole window until all reads have been issued.

The six fixed coefficient banks are source15 upper/lower, source30 upper/lower,
and source60 upper/lower. `generate_starlink_direct_coarse_banks.py` regenerates
all 396 original Q15 taps and checks each bank's digest against the already
retained numerical-study provenance. The packed ROM contains 66x192-bit
six-coefficient groups. Its SHA-256 is
`6abcf15cab2624829e53c5c4669028db65a68a08d16d1420bf0bbb89797c1f4b`.
The ROM is fixed; this interface does not upload or mutate coefficients.

A valid bank configuration is acknowledged atomically and fences all pending
work, including a completed but unconsumed output. The coincident source beat,
if any, starts the new segment under that acknowledged bank. Invalid banks are
rejected. Each result carries `{generation[28:0], bank[2:0]}` plus its raw
timestamp. A bank's timestamp stride changes in the same transaction.

Explicit source gaps always increment a saturating gap counter, even when
coincident with a bank configuration or flush. The old expected-timestamp
comparison alone is inapplicable on such an intentional fence. Timestamp
discontinuities otherwise count as gaps. History expiry counts separately.
Both fault types flush pending arithmetic/output and restart history; the
coincident beat can seed the new segment. Fault counters survive local fences,
and generation changes expose the discontinuity to a future consumer.
This restart is not a healthy phase-map continuity claim.

The 29-bit generation never aliases silently. Further bank changes are rejected
at its maximum. A fence requiring another generation saturates it and latches
`identity_exhausted`; output is suppressed, configurations are rejected and
incoming samples remain counted but invalid until external reset. A native
wrapper must give that reset a new session/reset identity and invalidate old
maps before accepting generation zero again. Such a wrapper is not implemented.

## Executed tests

The independent testbench uses four-product integer dot products for every
complete window; it does not use the MAC's Gauss decomposition or feeder
addresses to calculate expected results. It checks stored input timestamps,
bank/generation identity, ordering and total accepted/emitted counts.

The final replay passes with 72543 source beats, 71047 exact results, 15 fence
events, three deliberately induced history expiries, four gap events, 5763
stalled-output cycles and 819 concurrent read/write collision checks. It covers:

- Both edges and all three declared timestamp strides; raw timestamp wrap;
  and 66050 consecutive source samples crossing canonical ordinal wrap.
- A supported recurring stall pattern: 100 blocked service clocks after each
  1000 ready clocks while canonical source arrivals continue.
- A longer 400-source-beat output blockage that repeatedly exhausts history.
  Expired work is discarded with fault/generation evidence, never published
  with overwritten samples. Later surviving windows match their exact input.
- Explicit gap and timestamp mismatch; config+gap and flush+gap coincidences;
  bank replacement with an old result held; rejected bank IDs; reset/flush of
  pending work; and a forced generation rail followed by rejected config,
  continued input counting, no output alias and external reset recovery.

Development probes are also retained as negative observations: an initial
90-source-beat blockage labeled as a non-expiring bank-switch test exceeded
the 62-sample nominal history spare and correctly caused expiry. The final
bank/reset tests use 30 blocked source beats and separately retain the
400-beat expiry test. A held-valid check was moved one simulation time unit
after changing source-valid at a falling edge so combinational fault gates
settle before inspection. These changes did not alter numerical tolerances or
the required source input rate.

This replay spans about 5 ms of simulated service time, not a 120 ms visit or
300-second scanner. It establishes synchronous feeder/history behavior under
the stated traffic and faults; the failed physical result below prevents a
claim of achieved 15 MS/s in silicon.

## Actual combined resource and timing measurement

Vivado 2022.2, `xc7z010clg400-1`, maximum two threads, the same 5 ns clock and
declared input/output delays as the original MAC-only slice. Both runs include
actual placement and route, all counters, bank ROM, histories and MAC.

| Feeder revision | LUT | FF | Slices | DSP | BRAM tiles | Control sets | Setup WNS | Hold WHS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Initial, before coincident-gap / identity-rail corrections | 2465 | 2813 | 790 | 18 | 4 | 19 | −2.714 ns | −0.743 ns |
| Corrected and tested source | 2354 | 2814 | 744 | 18 | 4 | 21 | −3.161 ns | −0.742 ns |

Both infer exactly six RAMB18 sample replicas and one RAMB36 timestamp store.
The coefficient ROM is implemented in logic. Both physical gates fail; all
check-timing categories and methodology violation counts are zero. The initial
source and reports are retained, and no false paths or relaxed delays were
introduced for the corrected result.

The corrected worst setup path is
`expected_timestamp_reg[4]/C -> expiry_now`: WNS −3.161 ns, data delay 5.948 ns,
comprising 2.320 ns logic (39.001%) and 3.628 ns routing (60.999%). A failing
internal path also exists:
`next_start_reg[0]/C -> coefficient_read_reg[13]/R`, WNS −2.865 ns, data delay
7.247 ns = 2.390 ns logic + 4.857 ns routing. Failure is not limited to a
diagnostic output port.

The corrected worst hold path is
`sample_i[0] -> history[2].samples_reg/DIADI[0]`: WHS −0.742 ns, data delay
0.924 ns entirely in routing. This remains an OOC input-to-BRAM hold failure
under the declared delays; it is not waived or interpreted as board closure.

For comparison, the initial worst setup path was
`write_sequence_reg[0]/C -> output_valid`, data delay 5.501 ns = 2.155 ns logic
+ 3.346 ns route. The feeder's actual gap/expiry/publication controls expose
timing cost that the MAC-only +0.453 ns setup result omitted. Fewer LUTs in the
corrected run did not improve its worst timing. No additional physical rewrite
or lower-clock projection was attempted in this bounded study.

## Remaining costs and reproduction

Normalization is explicitly unimplemented and unmeasured in this continuation.
Exact sliding sample energy, per-bank coefficient energy selection, wide
direct correlation squares, the 69-bit ratio and ties-to-even eight-bit score
division still require hardware. The existing 18-bit BFP score-preparation
block cannot accept a 40-bit direct accumulator unchanged. The 2354-LUT /18-DSP
figure therefore must not be advertised as a complete score engine cost.
Input CDC, sparse full-rate fine timing, phase-map integration, pilot export,
native ABI ownership/reset, complete-receiver route and radio qualification
are also outside this slice.

Reproduce the bank ROM from firmware root with the existing Python environment:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python tools/generate_starlink_direct_coarse_banks.py --output hdl/library/starlink_pss_direct_coarse
```

From `hdl/library/starlink_pss_direct_coarse`:

```sh
iverilog -g2012 -Wall -s tb_direct_feeder -o build/direct_feeder.vvp starlink_pss_direct_mac6.v starlink_pss_direct_feeder.v tb_direct_feeder.sv
vvp build/direct_feeder.vvp
```

For physical reproduction, invoke `synthesize_feeder.tcl` from a fresh output
directory using Vivado 2022.2 and its existing compatibility-library path.
The script returns failure on the measured setup/hold violations. Retained
evidence under `hdl/library/starlink_pss_direct_coarse/evidence/feeder/` includes
the source identities, test receipt, initial/corrected full physical reports,
transcripts, source snapshot and hashes. Large DCPs remain under ignored
`build/`; these are experimental results, not release qualification.

No full receiver build, radio access, PPU edits, deployment, remote push or
main merge occurred. Both FPGA stages, independent 2.5 MS/s IIO GLRT,
.18-before-Ethernet-.17 and the full source-rate/scanner objective remain
required and unqualified by this experiment.
