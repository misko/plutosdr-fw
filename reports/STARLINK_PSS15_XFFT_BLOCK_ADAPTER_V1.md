# Starlink PSS15 strict XFFT block-adapter checkpoint

## Verdict

PASS for the vendor-IP-independent 512-point XFFT control and metadata
boundary. The source is simulation-qualified for both forward and inverse
configuration, and one default forward instance passes the canonical Vivado
2022.2 Zynq-7010 100 MHz post-opt out-of-context gate.

This is a source-only experimental checkpoint. It is not eligible to merge,
release, build into a radio image, or persistently flash. It does not
instantiate an XFFT core, package the PSS coefficient ROM, connect the
forward/product/inverse chain, accept live RX IQ, produce a PSS timing result,
or qualify 15, 30, or 60 MS/s hardware operation. No radio was contacted.

This superseding manifest also corrects one provenance-only error in the
immutable candidate-score-path manifest: `submodule_hdl_quantulum` contained
the candidate HDL tag object `70142c3d...`, while the actual unchanged
`hdl-quantulum` gitlink was and remains
`364b3dc7e770c3971d1f41a75c00e6cae76e2e6d`. The old tag is not rewritten.

## Frozen interface contract

One adapter owns one generated Xilinx XFFT interface and allows at most one
512-sample block in flight. It provides these explicit boundaries:

- the generated core's active-low reset remains asserted through flush and
  for two acquisition-clock releases afterward;
- the compile-time direction word is accepted before application data opens:
  bit zero is one for forward and zero for inverse, with all other bits zero;
- every application input position and TLAST is checked, and the 64-bit block
  start remains constant for the complete input block;
- the status channel is always ready after reset, its upper padding is zero,
  and exactly one per-frame block exponent belongs to the active block;
- XFFT data cannot be published until that status has arrived;
- natural-order TUSER index, TUSER padding, TLAST, and block exponent are
  checked on every output, with stable absolute block identity;
- an orphan/duplicate/malformed status, frame-event identity error, XFFT TLAST
  event, status-channel halt, or bad input/output metadata latches quarantine;
- malformed output is gated in the same cycle and consumed after quarantine,
  while malformed application input never reaches the core; and
- data-input/output halt events are exported as telemetry but are not hard
  faults because legal AXI backpressure can cause them.

These choices match the generated 24-bit fixed-point, block-floating XFFT
shape already frozen by the retained IP-generation evidence. AMD PG109 states
that TUSER carries per-sample index and block exponent in the data channel, and
that block-floating status is sent at frame start. Those are precisely the
two independent metadata copies checked here:
[Data Output Channel](https://docs.amd.com/r/en-US/pg109-xfft/Data-Output-Channel),
[Status Channel](https://docs.amd.com/r/en-US/pg109-xfft/Status-Channel).

## Deterministic simulation

`tb_starlink_pss_xfft_block_adapter.sv` uses an intentionally simple mock core,
not a behavioral substitute for the FFT arithmetic. It checks:

- forward configuration `0x01` and inverse configuration `0x00`;
- configuration-before-data and the two-cycle post-flush reset stretch;
- one complete 512-sample input and 512-result output block;
- exact complex-lane packing, natural-order index, TLAST, exponent, and 64-bit
  block-start identity;
- independent core-input and downstream-output stalls with stable payload;
- a first result held until block-floating status arrives, followed by a
  same-cycle status/result retirement;
- nonfatal input/output halt telemetry; and
- five separately flushed quarantines: application TLAST, orphan status,
  XFFT missing-TLAST, status-channel halt, and wrong output index.

The passing line is:

```text
XFFT_ADAPTER_PASS input_blocks=2 output_blocks=1 published=512 directions=forward_inverse reset_stretch=2 config_before_data=1 status_before_output=1 stalls=1 input_faults=1 output_faults=1 status_faults=2 core_tlast_faults=1 flush_recovery=1
```

The acquisition regression now contains 14 passing RTL simulations, including
the already frozen candidate-score-path integration.

## OOC implementation gate

The first synthesized form correctly failed the gate: coupling all possible
fault sources into same-cycle XFFT output publication created a 17-level path
and setup WNS `-1.018 ns`, with a TIMING-16 methodology violation. The final
architecture uses the proven one-block lifecycle: application loading cannot
coincide with result unloading, so input-phase faults are registered before
the output phase can open; only status/output faults that can coincide with a
result remain in its immediate publication gate.

The final Vivado 2022.2 post-opt, unplaced OOC result for one adapter at 100 MHz
on `xc7z010clg400-1` is:

| Resource/check | Result |
|---|---:|
| LUT | 103 |
| Registers | 111 |
| RAMB36E1 / RAMB18E1 | 0 / 0 |
| DSP48E1 | 0 |
| Setup WNS | +2.328 ns |
| Hold WHS | +0.269 ns |
| Methodology violations | 0 |
| Nonzero `check_timing` categories | 0 |

The frozen summary is
`reports/starlink-pss15-xfft-block-adapter-ooc-summary.txt`, SHA-256
`599ca4afa10a9164227834956e45f7e34d8084a4436fa267aa52563cc0570501`.
This is not routed-shell timing evidence.

Two adapters add 206 LUTs and 222 registers to the previous isolated planning
subtotal. The updated additive subtotal is 8,056 LUTs, 12,150 registers, 37.5
BRAM tiles, and 32 DSP48E1s: 45.8%, 34.5%, 62.5%, and 40.0% of the Zynq-7010,
respectively. It still excludes coefficient ROM, generated-XFFT composition
control, CI16 conversion glue, phase generation, AXI/CDC/control, debug, and
placement/routing margin.

## Source lock and next gate

The adapter is source-locked at HDL commit
`b8657819e56c9a2b836319e9b9b8596fc4ce3204`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-xfft-block-adapter-v1` on the
experimental do-not-merge branch. Firmware-main guard PR #90 passed all five
required checks and protects only that exact gitlink identity at merge commit
`68ef649d2fd76b62f437148a222f0881d50ea7f2`; the identity is also bound by the
source manifest.

The next gate is intentionally larger but still replay-only: instantiate the
two generated XFFT cores through these adapters, package a hash-locked
upper-edge coefficient ROM, connect scheduler to forward FFT to spectrum
product to inverse FFT to the candidate-score tail, and compare every
intermediate and all 447 final scores against the independent CI16 oracle.
Phase-map connection, full RX-shell routing, and radio qualification remain
later gates.
