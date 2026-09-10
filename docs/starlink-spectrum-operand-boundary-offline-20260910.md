# Elastic spectrum operands: isolated offline prototype

The default-off standalone wrapper passes29 new offline tests plus23 retained
rounding/product tests (52 total). It is not integrated into the bank or
receiver. No actual FFT, synthesis, placement, routing, radio or PPU operation
was performed. Physical AREG/BREG mapping is not established by this report.

Independent FW/HDL worktrees:
`/tmp/starlink-coarse-alternatives.Y3JzOI/operand-boundary` and its`hdl` child,
branch`codex/starlink-rx-only-do-not-merge-operand-boundary`.
Starting pins FW`90fc402229654bbba1de973eb03bf2a56c81e55c` /
HDL`ce9c863ab00228378831dbdb395db1c49554e90b`. Both requested branch names and
the new path were verified absent before creation. The bank-native-paired and
primary worktrees were not edited.

## Contract and intended cut

The existing full-bank observation is a BRAM-to-DSP operand path with
AREG1/BREG0; isolated rounding checkpoints instead had AREG0/BREG0. Neither
observation proves that a new logical operand register will infer the intended
DSP input registers. This experiment creates the required true logical stage
before any physical inference claim.

`starlink_pss_spectrum_product_operand_register.v` wraps the unchanged arithmetic
module. REGISTER_OPERANDS defaults0; BOUNDARY_ROUND_SAT defaults0 and is forwarded
to that actual module. Mode0 is direct wiring with no added valid/payload state.
Mode1 captures both complex operands (all four signed components) together
with bin9, exponent5, last1 and start-index64 under one ownership bit.

The slot is ready when empty or when the arithmetic core can accept it.
External input_ready is additionally gated by resetn and !flush, matching the
core contract. A simultaneous dequeue/refill transfers the old token into the
core and captures the new token. A blocked occupied slot cannot overwrite
either operand or metadata. Reset and flush synchronously clear the entire
slot; input_ready falls immediately while reset/flush is asserted. Core reset,
flush and output behavior are forwarded unchanged, not asynchronously masked.

| No-stall latency convention | Default0 | Registered1 |
| --- | --- | --- |
| Acceptance edge to output-visible edge, elapsed clocks | 2 | 3 |
| Pipeline edges including acceptance edge | 3 | 4 |
| Elastic token capacity | 3 | 4 |

Thus option1 adds exactly one real no-stall clock. No old CSV latency or
expected cycle values were edited. Under stalls the absolute timing differs
according to the extra owned slot; packet equality alone is not timing
equivalence. overflow_pulse retains the core's **output-insertion** meaning,
not downstream acceptance. It can pulse when an empty output slot receives a
saturating result even if downstream ready is0, then clears on the next clock
while output_overflow/payload remain held. The extra cycle and stalls change
absolute fault-observation timing: full-bank current/late raw fault veto,
final-token publication, reset and private ownership must be requalified before
integration. No fault fence is removed or shortened here.

## Logical state budget, not mapped resources

Added state is4D+79 payload bits plus1 valid bit: **4D+80**. That is152 bits at
D18 (72 operands+79 metadata+1 valid),176 atD24, and0 in default passthrough.
There is no added logical multiplier or RAM and no arithmetic change. Actual
fabric FF/DSP-register allocation, control-set cost, placement and timing have
not been measured. The extra ready path remains combinational and also needs
bank-level timing review; this is not a ready/fault cone redesign.

Arithmetic source remains byte-identical to the pinned module, SHA256
`4f9046d0efc395d68caa9b63911fcf5c18ab335b1f2707ad19d3794e0cc2329b`.
REGISTER_OPERANDS invalid−1/2/X/Z values fail closed. Forwarded rounding-option
invalid−1/2/X/Z values retain the core guard; option1 rounding rejects width1.
Default rounding still supports width1, including registered operands.
Nonpositive widths cannot elaborate/admit a design; invalid core replication
widths can fail elaboration before the wrapper's time-zero positive-width guard.

## Executed tests and preserved evidence

Initial new suite:25 PASS in1.85s, unique`operand-boundary-offline-v1`.
After adding omitted-default/actual forwarding/nonpositive-width checks and
removing an unused test import, final new29 plus retained23 tests passed:
52 PASS in13.16s, unique`operand-boundary-offline-v2`. Ruff passes. No unexpected
functional failures occurred; all six intentionally faulty wrapper variants
remain archived as rejected mutants, not passing RTL.

Each of nine healthy width/round profiles executes5010 cycles with both operand
modes: D1/round0 and D2/8/18/24 with round0 and1. Python arbitrary-precision
sign-magnitude nearest-even complex multiplication generates1024 operand,
metadata and expected-result records per profile. An independent elastic-stage
model checks only accepted tokens, exact data/metadata/overflow, occupancy and
accepted=emitted+discarded+outstanding every edge. No-stall output ages must be
exactly2/3 elapsed clocks. All default public outputs, including invalid payload
retention and pulse timing, are additionally compared cycle-for-cycle against
the original core. Omitted parameter defaults and actual child parameter
forwarding are separately inspected in elaborated unit tests.

Tests cover full backpressure, simultaneous dequeue/refill, random bounded
stalls, busy reset/flush, hostile X/Z invalid bubbles, final drain, and a directed
saturating last token held at output then reset, followed by a fresh saturating
last token held then flushed. Pulse insertion and held-output stability are
checked independently. Mutations of ready logic, stage validity, kernel
operands, start metadata, reset validity and occupied-slot overwrite all fail.

For D18, both rounding choices observe the same counts:

| Counter | Default0 | Registered1 |
| --- | --- | --- |
| Accepted / emitted / discarded | 1768 /1682 /86 | 1785 /1671 /114 |
| Simultaneous dequeue/refill | 1733 | 1748 |
| Stalled output clocks | 3131 | 3112 |
| Overflow insertion pulses | 104 | 102 |
| Saturating-last reset / flush witnesses | 1 /1 | 1 /1 |
| Final outstanding | 0 | 0 |

Different accepted/discarded counts under the same timed stall/reset profile
are expected from the extra slot and are explicitly conserved, not concealed
by comparing unequal trace positions.

Archive:`reports/experiments/20260910-operand-boundary-offline-evidence.tgz`,
SHA256`10213e850e4958d2f7b5e041b62cd4461874eceeb84f150b1bf2ae4bda089176`.
It contains268 safe unique regular files (916318bytes), every hash verified:
both new-run generations' source/vector freezes, healthy and mutation logs,
generated parameter probes, both policy XML receipts and final source copies.
Each healthy/mutation case freezes five inputs before execution—core, wrapper,
SV bench, Python generator/test and vectors—and verifies all five afterward.
The retained large legacy rounding-vector files remain in the unique v2 build
directory and prior rounding archives; they are not duplicated here. This
scope does not claim a full Python-import or installed-toolchain closure.
All artifact hashes and test rows are in
`20260910-operand-boundary-offline-results.json`.

Next, an independently reviewed isolated physical A/B script may test input
register inference using the existing175MHz OOC budgets. No such measurement
has run here. Isolated mapping still cannot qualify the real bank BRAM path,
full receiver timing or source15/30/60 coarse/native/pilot deployment. Both
detectors, exact numerical references, native original samples,2.5MS/s pilot,
.18-before-.17 and the eight-target/120ms/300s objectives remain unchanged.
