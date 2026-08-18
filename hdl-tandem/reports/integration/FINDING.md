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
