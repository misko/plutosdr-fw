# Combined control refactor: routed improvement, timing still FAIL

The actual-qualified combined private-offer/closed-input candidate has now been
synthesized and routed with the unchanged prior recipe. **It is not a release
candidate:** WNS is -2.697 ns, TNS -981.622 ns, with 848 failing setup endpoints.
Hold timing passes at +0.037 ns with zero failing hold endpoints. No radio was
changed or flashed.

| Measured isolated route | Prior retained | Combined refactor |
|---|---:|---:|
| Worst setup slack | -4.068 ns | -2.697 ns |
| Total negative setup slack | -1952.796 ns | -981.622 ns |
| Failing setup endpoints | 1266 | 848 |
| Worst hold slack | +0.052 ns | +0.037 ns |
| LUT / FF | 2334 / 4768 | 2333 / 4764 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

The 1.371 ns worst-slack improvement is measured, but does not close timing and
is still worse than the earlier P1 route (-1.492 ns). All 7233 nets are fully
routed with zero routing errors. Pulse-width slack is +1.830 ns. Routing/tool
success is distinct from the failed timing gate.

## Qualification and unchanged comparison conditions

The candidate first passed [the actual vendor FFT campaign](20260910-retained-control-actual-parent.md).
Root then independently passed the 32-test synthesis preparation gate in 1.55 s
(original 34198, exit 0), with all 110 prepared files unchanged. A separate
read-only reviewer confirmed exactly four reviewed runtime replacements plus
twelve unchanged runtime files, correct option forwarding, and no reference or
testbench substituted into synthesis.

Root synthesis **56000** completed exit 0 in **187.76 s**. The exact 16-runtime
hierarchy has no black boxes: 2242 LUT, 4759 FF, 21 DSP and 15 RAMB18. Relative
to prior retained synthesis this is +3 LUT/+1 FF with unchanged DSP/RAM. The
single FFT remains 1205 LUT/2989 FF/17 DSP/11 RAMB18. Root verified runtime pins,
both options, source/copy integrity, generated FFT identity, effective constraints,
all eight clock-pair path reports and mapped hierarchy before authorizing route.

Root independently replayed the unchanged eight route-preparation tests (exit 0,
0.06 s). The unchanged runner then routed the audited synthesized checkpoint:
original **96174**, exit 0, **62.76 s**. The source checkpoint and both runner
copies are unchanged. Root checked raw path reports, timing summary, utilization,
route status and inherited constraints against the recorded results.

Part xc7z010clg400-1, factory, two threads, rebuilt/AreaOptimized_high/OOC synthesis,
control-set threshold 4, and opt/place/phys-opt/route sequence are unchanged.
There are no new clock groups, false paths or multicycle exceptions.

## Remaining critical control path

The worst same-domain path is now:

`product_bank.metadata_out_hold[8] → input identity/fault → epoch/cutover/owner
fault logic → retained_owner.fault_reasons[6]/D`.

It has ten LUT levels and 8.085 ns data-path delay: 1.690 ns logic plus 6.395 ns
routing. The destination is no longer the prior private descriptor clock enable.
Other top paths reach retained publication/reservation state, cutover state and
the completion receipt. Kernel-ROM block-start enables remain in the top twenty
at approximately -2.422 ns; this refactor did not eliminate every ROM control path.

Clock-pair setup / hold slacks:

- 100→100: +2.497 / +0.110 ns.
- 100→175: -0.540 / +0.134 ns.
- 175→100: -1.276 / +0.130 ns.
- 175→175: -2.697 / +0.037 ns.

Five critical CDC findings remain (four CDC-1 and one CDC-10), plus 139 warnings.
The isolated model still lacks 114 input and 124 output delays. The rounded
independent 100/175 clocks are not a qualified board-derived clock model.
No-clock/internal-unconstrained/loop checks are zero, but that does not resolve
the explicit external-I/O and CDC gaps. Full receiver 175 MHz clock integration
and actual AD9361 RX calibration remain separate required gates.

Next: inspect the measured fault-control cascade and propose a bounded stage
separation that preserves current fault fencing and publication authority.
In parallel the checked-product final-drain correction passes independent76
offline tests; its new actual replay has not yet run. No fault checks, service
limits or deployment requirements have been relaxed.

## Exact artifacts

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:

- `retained-control-synthesis-prepared-v1`: 110-file preparation, inventory
  `3590d4db36dd313a1db55419f46f1897bf8b588756e8b406f55537b1d7c135ee`.
- `retained-control-synth-parent.9xhaMMns`: parent gate, owner, synthesis and audit.
  Synthesized DCP SHA256:
  `193cf14408ca768d403f1ef4bba913c07bf24a94bb88fb647941b95a03dd1482`.
- `retained-control-route-parent.rza0KS8U`: parent gate, owner, route and audit.
  Routed DCP SHA256:
  `2ec838aa9a0a6f5ee297e506a07a842a1aa597f0e08241dc5bbf93b9493c1f3f`.
- `checked-drain-parent.FkKDoLe7`: independent35 bounded scheduler tests.
- `checked-drain-prep-parent.TQPsrJdl`: independent76 v2 preparation/scheduler
  tests, 34 live pins and 89 prepared pins unchanged; no vendor execution.

The initial root route-audit script rejected the indented RAMB18 resource label.
Its source and failure note are preserved; accepting label indentation while
keeping exact column/value checks corrected only the audit script. No vendor
report or failed timing result was changed.
