# Stage 3 integration: the block does not fit on the 7010 alongside RC17

Five full place-and-route attempts against the measured RC17 baseline. The
design is functionally complete and every simulation suite passes; the
obstacle is physical capacity, which §6 said only a real implementation
could settle.

| # | Variant | Slices needed | Available | Over |
|---|---|---:|---:|---:|
| 1 | as designed (554 LUT / 1227 FF / 2 BRAM) | 2417 | 2314 | 103 |
| 2 | first reduction (448 / 812 / 2) | 2352 | 2318 | **34** |
| 3 | + control-set opt threshold 16, top run only | 2425 | 2313 | 112 |
| 4 | + threshold on every OOC synth run | 2425 | 2313 | 112 |
| 5 | + datapath narrowing (432 / 688 / 1.5) | placement density failure | | |

## What each attempt establishes

**Raw capacity is not the headline.** LUT and FF totals stay comfortably
inside the §6 guardrails throughout — the projected total is about 77% LUT
against a ~82% ceiling. The binding constraint is *slices*, and the baseline
already occupies most of them.

**Control-set optimisation made it worse, twice.** Raising the threshold
converts enables into logic, which trades flip-flops for LUTs; with LUTs
also tight that is a losing trade here. Attempt 3 applied it only to the
top-level run and changed nothing, because ADI synthesises each block-design
cell out of context in its own run — attempt 4 applied it everywhere and
cost 112 slices instead of 34. Recorded because the property looks like the
obvious remedy for this placer error and is not.

**Narrowing the datapaths bought real area.** pwr_period 32→20 bits, the
event sequence 32→16, the counters 16→8, the event record to its exact 104
bits, and the CDC bus's redundant hold register removed where the source is
already stable: 554→432 LUT and 1227→688 FF, a 44% reduction in flops. It
was not enough, and attempt 5 fails on placement density rather than slice
count — the device is simply full.

## The fork this forces

The remaining options are architectural, not tuning:

1. **Drop the event-capture half.** Tandem gain control needs the ownership
   mux, policy, pulse generator and runtime enable. It does not need the
   event FIFO, the sequence counter, the record registers or most of the AXI
   read path. That is the largest single block of area left and it maps
   exactly onto the phase-only scope already discussed. The cost is the
   exact per-sample gain series, which was the other half of the motivation.
2. **Floorplan.** §6 permits it "only where evidence supports it"; there is
   now evidence. It does not create capacity, only redistributes it, so it
   is unlikely to close a density failure on its own.
3. **Reduce something in the existing design.** §6 forbids removing safety
   or metadata functions to force a fit.

Option 1 is measurable and reversible. Nothing here is wasted either way:
the controller, the CDC layer, the AXI slave and seven test suites all stand.


---

## Resolution: EVENTS=0 fits

The fork was measured rather than argued. An `EVENTS` parameter compiles out
the whole event-capture path -- FIFO, sequence counter, record registers and
overflow tracking -- which tandem gain control itself does not depend on.

| Variant | LUT | FF | BRAM |
|---|---:|---:|---:|
| EVENTS=1 | 432 | 688 | 1.5 |
| EVENTS=0 | 331 | 579 | 0 |

Integrated, EVENTS=0 **places and routes**: 13,386 LUT against a 13,088
baseline, 76.06% against a ~82% guardrail, BRAM back to 6, DSP untouched at
72. The +298 LUT cost is modest.

## What remains is timing, and it is not the tandem block's fault

The routed design misses timing, and every failing path is inside the
existing `axi_ad9361` IP on the 100 MHz AXI clock:

    source  axi_ad9361/i_up_axi/up_wdata_int_reg[*]
    dest    axi_ad9361/i_tdd or i_tx register
    delay   12.02 ns, of which 11.57 ns (96%) is routing
    logic levels 0

Zero logic levels and 96% route delay is a congestion signature, not a slow
path. Adding a sixth AXI slave pushed an already-full device past the point
where the router can keep `axi_ad9361`'s internal nets short. The baseline
closes at **+0.504 ns**, so there was almost no margin to give away.

Attempts so far: default directives -2.391 ns; `AltSpreadLogic_medium` made
it **worse** at -3.649 ns with 235 failing endpoints, because spreading logic
lengthens routes on a full device. The current attempt targets the actual
signature -- driver replication via `phys_opt_design AggressiveExplore`, plus
`route Explore` and post-route physical optimisation.

If directives cannot close it, the evidence now supports floorplanning under
§6: the failing paths are localised to one IP, so a pblock keeping the tandem
block away from `axi_ad9361` is a targeted remedy rather than a guess.


---

## Timing closure: five attempts, and doing nothing wins

With EVENTS=0 the design places and routes every time. It never meets timing.

| Attempt | WNS | TNS | Failing |
|---|---:|---:|---:|
| **default flow** | **-2.391** | | **best** |
| `AltSpreadLogic_medium` placer | -3.649 | -435 | 235 |
| `phys_opt AggressiveExplore` + `route Explore` + post-route | -3.895 | -587 | 326 |
| pblock to `CLOCKREGION_X1Y1` | -3.740 | -630 | 394 |

Four interventions, four regressions. On a device at 76% LUT with a baseline
that closes at +0.504 ns, every extra optimisation or constraint churns
placement and lengthens routes rather than relieving them. That is a
consistent result across independent techniques, not a tuning accident.

## What the failure actually is

Every failing path is inside `axi_ad9361`, on the 100 MHz AXI clock, from
`i_up_axi/up_wdata_int_reg[*]` to that IP's own register banks. Zero logic
levels; ~96% of the delay is routing. The tandem block is not on any failing
path -- out of context it closes with +10.7 ns of slack.

The mechanism is capacity, not logic: adding a sixth AXI peripheral scatters
`axi_ad9361`'s internal register banks, and its internal write-data fanout
then cannot be routed short enough. **RC17 does not have the timing headroom
on this device to accept an additional AXI peripheral.**

## Options that remain, none of them tuning

1. **Attach without an AXI slave.** The interconnect port is the cause. The
   existing `up_adc_gpio_out`/`up_adc_gpio_in` pair is fully consumed --
   bit 0 to the decimator, bits 31:1 to `timestamp_every` -- but
   `timestamp_every` almost certainly does not need 31 bits, so narrowing it
   would free a window. That changes a shipped register ABI and needs its own
   review.
2. **Accept a larger device.** Not available for existing hardware.
3. **Reduce the existing design.** §6 forbids removing safety or metadata
   functions to force a fit.

## What is not blocked

This is a Stage 3 result. It does not block Stage 1's design review, Stage 4's
runtime work, or Stage 5's metadata and host work, none of which depend on a
bitstream that fits. Those proceed independently.


---

# CORRECTION: the blocker was a missing constraint, not device capacity

Everything above this line diagnosed a capacity problem. **That diagnosis was
wrong.** With one constraint added, the same EVENTS=0 design closes timing at
**+0.780 ns with zero failing endpoints** — better than the RC17 baseline's
+0.504 ns.

| | WNS | Failing endpoints |
|---|---:|---:|
| RC17 baseline | +0.504 | 0 |
| tandem, five placement + four timing attempts | **-2.391** best of nine | 230–394 |
| tandem, one constraint added | **+0.780** | **0 of 53,382** |

## What was actually wrong

`clk_fpga_0` (100 MHz, PS PLL) and `rx_clk` (61.44 MHz, sourced from the
AD9361) have no phase relationship whatsoever. Nothing in the project declared
that. The baseline never needed it: it has only **8** endpoints between the two
domains and they pass with +14.9 ns, so the omission was invisible.

The tandem block adds **170** more. Every one of them was being timed as a
single-cycle synchronous transfer between unrelated clocks — something no
placer or router can ever achieve. Hence the signature the earlier analysis
misread: zero logic levels, ~96% routing delay, and *nearly every* cross-domain
endpoint failing (57 of 65 one way, 105 of 113 the other).

The block's own out-of-context runs closed with +10.7 ns because
`hdl-tandem/tandem_agc_axi.xdc` declares exactly this:

    set_clock_groups -asynchronous -group [get_clocks s_axi_aclk] \
                                   -group [get_clocks l_clk]

That file is **never added to the integrated project**. The block is
instantiated with `create_bd_cell -type module -reference`, and a plain module
reference carries no constraints — only packaged IP does. So the design was
correct, the constraint existed, and it simply never reached the build.

## Why nine attempts all made it worse

Because they were being asked to fix a constraint bug with placement. Four
successive interventions each *regressed* the reported slack:

| Attempt | WNS |
|---|---:|
| default flow | -2.391 |
| `AltSpreadLogic_medium` | -3.649 |
| `phys_opt AggressiveExplore` + `route Explore` | -3.895 |
| pblock to `CLOCKREGION_X1Y1` | -3.740 |

A consistent regression across four independent techniques should have been
read as evidence that the target was not congestion. It was recorded above as
"a consistent result, not a tuning accident" — correct observation, wrong
conclusion drawn from it.

The five *placement* failures earlier in this document are a separate matter
and were real: at EVENTS=1 with the original datapath widths the block genuinely
did not place. Whether it places now, with the placer no longer distorted by
170 impossible paths, is being retested rather than assumed.

## The constraint

In `system_constr.xdc`, `set_max_delay -datapath_only` rather than
`set_clock_groups -asynchronous`. Every crossing in `tandem_cdc_lib.v` is a
handshake or gray-coded transfer whose data is stable for many source cycles
before the destination samples it, so the setup relationship is meaningless —
but the skew between the bits of a bus is not. Declaring a false path would
drop that check too and permit a bus to be sampled mid-transition.

## What this invalidates

The "fork" above — drop the event-capture half, floorplan, or reduce the
design — was a choice forced by a bug. `EVENTS=0` was adopted on that basis and
is now being re-examined. Nothing else in the document's measurements is wrong;
the LUT, FF and BRAM figures all stand. Only the conclusion drawn from them
does not.
