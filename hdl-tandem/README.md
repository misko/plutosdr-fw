# Tandem AGC v2 RTL

Answers the project's single unbounded risk before the real controller exists:
does a block of this size and shape fit and close timing on a Zynq-7010 already
at ~74% LUT?

`tandem_agc_canary.v` is the real block's skeleton, not filler — the register
bank of design-contract §8, the 256×128 event FIFO of D-9, the real counter
widths, the pulse generator and ownership mux including tri-state, and the
3-stage detector conditioning. Only the policy truth table is a placeholder.

## Out-of-context synthesis, xc7z010clg400-1, l_clk @ 61.44 MHz

| Resource | Canary | Device | % | Plan §6 estimate |
|---|---:|---:|---:|---|
| LUT | 431 | 17,600 | 2.45% | 500–1,000 |
| FF | 502 | 35,200 | 1.43% | 600–1,400 |
| BRAM36 | 2 | 60 | 3.33% | ~1 |
| DSP | 0 | 80 | 0% | 0 |

WNS **+10.628 ns** against a 16.276 ns period, 0 failing endpoints of 792.
WPWS +7.638 ns.

Reproduce: `vivado -mode batch -source canary_ooc.tcl`

## Caveats

Out-of-context, so no placement pressure and no routing congestion. The
integrated place-and-route against the RC17 baseline is the real answer.
The canary also omits the AXI4-Lite slave (a standard component, roughly
100–200 LUT and 150 FF) and simplifies the policy truth table.


---

## Implementation

`tandem_agc_core.v` is the receive-clock controller and `tandem_agc_axi.v` is
the only control surface. It implements the forward-only `TAG2` register ABI
with a coherent 30-bit return crossing containing only software-observable
state. Epoch configuration is already AXI-local; retired-epoch and policy
diagnostic counters remain core-local for simulation and do not consume a
second pair of wide CDC register banks.
used by the Linux ownership driver; the v1 standalone register wrapper has
been removed so it cannot become a second control path.
`ad9361_gain_model.v` is a behavioural model of the part; every behaviour in it
is either cited to UG-570 or measured by experiment E-AGC1.

## Tests

    ./run_tests.sh

Six runs across five suites, all under Icarus Verilog:

| Suite | Covers |
|---|---|
| `tb_tandem_cdc` | reset bridges, coherent bus crossings, FIFO ordering, and explicit overflow |
| `tb_ad9361_model` | 27 checks that the model itself is faithful, including that a 1-ClkRF pulse is rejected and a 2-cycle one accepted |
| `tb_tandem_agc` (ratio 1.0) | closed loop at `rx_fir_dec = 2`, SPF production |
| `tb_tandem_agc` (ratio 2.0) | closed loop at `rx_fir_dec = 1`, the device-tree boot default |
| `tb_tandem_agc_stress` | §8.2 edge cases: randomised traffic, reset in every lifecycle state, disable at every pulse phase, chatter, long idle, FIFO overflow, sequence and 64-bit counter rollover, zero-cooldown request/pulse and HOLD handoffs, index-mismatch fault |
| `tb_tandem_agc_axi` | exact `TAG2` ABI, 32-bit kernel epoch, 16-byte post-change events, asynchronous AXI/RX clocks, and HOLD-low teardown ordering |

The twelve §10 assertions run continuously as procedural checkers
(`tandem_agc_checkers.v`) — Icarus has no SVA and this repository uses none.

## Out-of-context synthesis, xc7z010clg400-1, l_clk @ 61.44 MHz

| Resource | Core + regs | Device | % | Plan §6 estimate |
|---|---:|---:|---:|---|
| LUT | 516 | 17,600 | 2.93% | 500–1,000 |
| FF | 478 | 35,200 | 1.36% | 600–1,400 |
| BRAM36 | 2 | 60 | 3.33% | ~1 |
| DSP | 0 | 80 | 0% | 0 |

Against the measured RC17 baseline of 13,088 LUT this projects to **13,604 LUT
= 77.3%**, inside the ~82% guardrail, with DSP unchanged at 72/80.

Reproduce: `vivado -mode batch -source core_ooc.tcl`
