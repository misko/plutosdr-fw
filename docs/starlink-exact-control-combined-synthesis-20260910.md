# Exact111 OOC synthesis — completed, not routed

The single authorized synthesis completed: original owner handle **41784**, exit 0,
09:43:14.159463–09:45:03.062275 UTC, 108.9027 seconds. Raw Vivado exit is 0 and
the independent owner completion gate is true. Both source audits are 0. No
placement, route, retry, RTL change, receiver build or RF operation occurred.

Measured runtime/preparation pins: FW `b0b43802603c18472c65c159a36424785441af1a` /
HDL `26cc65a7f473ba3f528c90524df35ff0b25b7466`; launch-time report-only pins
FW `d934520ebcb02a647f26206bcfe9da8203d2a307` /
HDL `83ebba88f920d841c58050f9c4b03da8ecd29191`. Prepared SHA256SUMS remains
`99862b8d88414de6b2b4171df2a1a61bf5849ef2effed3c875de9904c366f158`.

Final checkpoint:
`/tmp/starlink-completed-input.5EaJuD/exact-control-combined-synth-v1/synthesis/fft_bank_owned_synth.dcp`
is 2,123,338 bytes, SHA256
`00cd669cee367f2ff9b3852d7fd05827ba64027ccd526f1f269cde5ddff630d9`.

Synthesized area: **1,970 LUTs, 4,478 FFs, 21 DSP48E1, 15 RAMB18E1**
(7.5 BRAM tiles), zero RAMB36 and zero black boxes. These are OOC synthesis
counts, not routed slice packing or complete-receiver savings. Physical control
set count and achieved setup/hold timing were not measured by this flow.

The synthesis log explicitly binds REGISTERED_SCHEDULING, DISTRIBUTED_FAST_FAULT,
PRIVATE_NEXT_START_SCRATCH to 1, plus the existing registered-only balanced,
payload-bubble and forward-retirement options. Actual clock report:
source_100 on `clk`, 10.000 ns; island_175 on `fft_clk`, 5.71400022506713867 ns.
Vivado reports the unchanged 1 ps rounding of the requested 175 MHz period.
No generated clocks are reported at the slice boundary. Part, factory,
AreaOptimized_high/OOC directives, two-thread settings and resource XDC are
unchanged. All 13 scope-declared before hashes, including the generated FFT
VHDL wrapper, match after synthesis; all seven RTL match the passed actual freeze.

**Unqualified CDC finding:** CDC-10 Critical 1 reports combinational logic before
the synchronizer from
`distributed_fast_fault.causes[8].cause_sticky_reg[8]/C` to
`fast_fault_slow_reg[0]/D`, island_175 → source_100. The report also contains
139 CDC-15 warnings and 5 CDC-3 informational crossings. This is not waived,
hidden or counted as CDC closure. `check_timing` retains 114 input ports without
input delay and 124 output ports without output delay; no-clock and unconstrained
internal-endpoint counts are zero. No achieved-clock or interface-timing claim.

Raw directory: `/tmp/starlink-completed-input.5EaJuD/exact-control-combined-synth-v1`.
Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-combined-synth-v1/`.
It preserves the original owner receipts/logs, all reported products and final DCP,
source/IP inventories, generated wrapper/XCI, child synthesis logs and Tcl.
The complete project remains local. Route consideration is a separate review;
no replacement eligibility or promotion follows from this result.
