# Paired 60 MS/s sample-support preparation

Scope: additive offline coordinate contract, not a runtime profile, numerical
common-source PSS cohort, service-budget proof, FPGA timing or RF qualification.
The existing 30 MS/s cohort, goldens and all RTL remain unchanged.

`tests/starlink_oracle/high_rate60_support.py` defines half-open raw intervals
with literal-integer and uint64 overflow checks. Two cascaded x2 acquisition
filters give raw support `[4*k-21, 4*k+22)` for canonical sample k. The second
filter operates on rounded CI16 outputs of the first; collapsing the cascade
to one FIR without intermediate rounding would not preserve its arithmetic.

Independent vectorized rotation/convolution at both stages matches the existing
streaming x4 oracle for both edges, including the full4096-output geometry.
Dropping either boundary raw sample removes exactly the corresponding one
canonical output. Tests also exercise absolute oscillator/decimation phases,
large coordinates, rejected invalid intervals, signed next-sample lead and
pilot history/support. No simulator or device was involved in these new tests.

## Fixed future-fixture geometry

| Evidence coordinate | Value |
| --- | --- |
| Original 60 MS/s source | `[34359735211,34359751634)`,16423 samples |
| Canonical 15 MS/s outputs | First8589933808,count4096 |
| Coarse start after768 canonical preroll | 8589934576 |
| Planned native center | 34359740384 |
| Original native capture | `[34359740256,34359740776)`,520 samples |
| Native coefficients / raw tuples / qualified tuples | 264 /257 /241 |
| Raw / qualified lag ranges | -128..128 /-120..120 |
| Default native minimum lead | 256 raw samples, measured from next sample |
| Selected pilot newest canonical endpoints | 8589934350,8589937416 |
| Selected pilot raw-center endpoints | 34359736324,34359748588 |
| Selected pilot full raw support | `[34359735227,34359749686)` |
| Selected pilot quantity / raw step | 512 CI16 samples /24 raw samples |

The source has10858 raw samples remaining after native capture. The native
correlation entails257*264=67848 tap/lag operations. This is an operation count,
not an engine-cycle bound: capture transfer, memory/MAC pipeline, reducer stalls,
publication, public reads and release must be measured/bounded separately.
No continuation-tail length or completion watchdog is frozen by this contract.

The pilot remains2.5 MS/s CI16:10,000,000 payload bytes/s, excluding IIO/network
framing. These tests verify support coordinates, not live DMA/IIO transport.

## Retained test runs

- Initial support suite:38 passed in0.22s, retained at
  `/tmp/starlink-highrate60-support.Cico1O` with raw log/XML/unique basetemp.
- Ruff initially requested import formatting only; corrected by Ruff, then PASS.
- Expanded support suite39 tests plus unchanged30 common-source and existing60
  DDC golden-vector suites:132 passed in4.03s, original33277 exit0, retained at
  `/tmp/starlink-highrate60-regression.sOQiHl` with raw log/XML/unique basetemp.

Next: construct and freeze a distinct60 common-source PSS/noise fixture and
conditioned60 kernel/FFT/native/pilot evidence; independently derive it; measure
native60 service under declared conditions before setting a finite source tail.
Then qualify public60 admission and the actual combined bank/native/pilot
harness. This work does not authorize a radio operation or bypass bank/full
receiver routing, IO/CDC/reset and RX-calibration gates.
