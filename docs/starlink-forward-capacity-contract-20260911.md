# Forward capacity contract — DO NOT MERGE / shadow only

The monotonic-reset candidate still has a ten-level release→product-ready→fault
path. This experiment investigates a parallel readiness expression using current
pipeline occupancy, not delayed readiness or removed fault gates. Runtime RTL,
FFT, buffers, clocks and synthesis profile remain byte-identical to that parent.

## Parallel expression

There are five pipeline occupancy bits before the private product-identity slot:
kernel output, registered operands, multiplier output, summed product and final
arithmetic output. Each empty stage offers capacity; otherwise the private slot
must be healthy and able to accept the next word. The factored expression keeps
the current kernel fault, product-slot fault, fast fault, final-slot restriction,
bank-derived refill permission and outer reset.

For a known binary outer reset, repeated reset terms in the serial ready chain
can be factored to its boundary. The algebra test compares serial and parallel
expressions over 4096 binary assignments, 90,112 individual X/Z substitutions,
and 16,384 randomized four-state assignments: 110,592 checks. It rejects dropped
reset/fault/occupancy/final-word conditions. Unknown outer reset is outside this
algebra contract; the existing common barrier emits a known binary running flag.

## Actual-FFT shadow and limits

The bench observes real pipeline state and compares parallel readiness with the
original unforced kernel-ready equation at every fast falling edge. It also
compares a hypothetical common-fault summary using that readiness. It changes
no control input, register, arithmetic or accepted transfer.

Existing tests deliberately force internal kernel readiness and guard summary
bits. The shadow records these overrides and every hypothetical fault-summary
difference; any difference without one of those explicit overrides is fatal.
These observations are NOT a proof that a replacement may ignore the overridden
fault inputs. All original fault tests still run against untouched runtime RTL.
Production integration must retain an explicit injection/diagnostic contract and
pass the full fault campaign; a shadow pass alone is not permission to deploy.

## Implementation gate

Version 2 completed both actual-FFT campaigns. The readiness equation matched
the original unforced expression on 503,564 main and 437,625 auxiliary checks.
Main recorded 493,734 healthy / 6911 external-fault observations, 16 deliberate
kernel-ready overrides, two summary-bit overrides and two hypothetical common
summary differences. Auxiliary recorded 432,630 healthy / 2736 fault observations
and no overrides or differences. Neither campaign had unexplained differences.
The 64,512 numerical records, CSV and service clocks remain parent-identical.
The corrected full regression passes 956 tests; this is observational evidence,
not a new runtime implementation or a timing-closure result.

The first auxiliary run stopped at product-stage boundary 11, which forces the
transport `product_valid` wire to X. The shadow mistakenly used that wire for
the arithmetic output occupancy, while the original ready chain uses the owning
`product.arithmetic.output_valid` register. Version 2 observes that register.
The forced-X stimulus and all runtime RTL remain unchanged. The failed version
and its source snapshot are retained, not reclassified as a pass.

If the shadow passes, export bounded occupancy/capacity observations through
explicit module ports, replacing bench-only hierarchical references. Prefer
factoring the producer's authoritative kernel-ready calculation itself over
giving the common fault summary a second, independently computed readiness.
That preserves the guard's original connection and the direct ready/summary
fault-injection tests, avoiding the shadow's explicitly observed exceptions.

An additive product-pipeline-full observation can combine the three arithmetic
valid registers and operand-valid register. A parallel capacity input to the
kernel can then replace the nested downstream-ready expansion while retaining
its outer reset/protocol-fault fence and its original output-stage enables.
Defaults keep the original calculation. Prove the opt-in public READY expression
and accepted transfers against the original on every edge; do not use this
capacity observation as independent publication authority. Repeat all current
fault/reset/actual-FFT tests and route the integrated candidate at unchanged
clocks. This experiment has no new routed implementation.

Native 60 MS/s fine search, 2.5 MS/s IIO inspection, full RX timing/CDC/calibration,
continuous RX and Ethernet qualification remain required. Hardware deployment is
still `.18` canary then `.17` through PPU Ethernet with rollback. No radios are
accessed by this experiment; `.20/.21`, primary firmware/HDL and PPU/main remain
unchanged.
