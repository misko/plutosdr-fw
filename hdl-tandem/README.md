# Tandem AGC — resource canary

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
