# Parallel kernel READY integration — DO NOT MERGE

This experiment integrates the previously observed capacity equation into the
authoritative kernel input READY. It does not replace the common fault summary
or disconnect any original guard input. Native 60 MS/s fine search and the
independent 2.5 MS/s IIO inspection stream remain required deployment features.

## Bounded implementation

- Arithmetic exposes the conjunction of its three owning valid registers.
  The operand wrapper combines that with its own valid bit. These are current
  occupancy observations; arithmetic, pipeline state and payload logic are exact.
- The top combines that occupancy with the existing private-slot idle output,
  current product-stage fault, fast fault, final-slot restriction and known
  bank refill permission. No hierarchical references occur in runtime logic.
- Joiner/kernel accept an explicit downstream-capacity input, enabled only by
  `PARALLEL_KERNEL_READY=1`. Defaults retain original behavior. The kernel keeps
  its reset/flush/protocol-fault fence and every original output-stage enable.
  Unknown reset selects the original equation rather than assuming a live epoch.
- The same kernel READY output remains wired to guards and transfer logic.
  Existing direct READY, summary-bit and transport-valid injections are unchanged.

Five of 22 runtime modules change; exact inverse checks reconstruct the parent
sources. Two arithmetic modules are copied from the hash-locked baseline into
the experiment source directory with only additive occupancy observations.
The prepare helper selects these versions without changing the baseline.

## Verification

The original-ROM comparison covers 4096 valid lookups, malformed metadata/order,
stalling and flush in default and enabled modes. False capacity is rejected.
The actual kernel expression is tested over 4096 four-state combinations/mode;
reset fallback, fault/flush fences and capacity mutants are rejected. The first
mutant harness matched both branches; its targeting was corrected without
changing RTL. Both original and corrected test artifacts are retained.

The frozen actual-XFFT bench independently checks exported occupancy and selected
unforced READY against the original expression, while preserving every existing
numerical, publication, cancellation, fault-injection and recovery campaign.
Main/auxiliary evidence and the synthesis opt-in must match before routing.
The previous observational marker now explicitly says runtime has changed.

## Physical and deployment gates

Measured result: 988 distinct tests pass (971 regression, six additional
four-state tests, eleven evidence checks). Actual main/auxiliary runs preserve
all 64,512 numerical records/CSV and service latency. Explicit occupancy and
selected-READY checks cover 503,564 main and 437,625 auxiliary observations.
Original direct-ready, forced-valid and summary fault tests still pass.

Routing completes, but regresses: WNS −1.434 ns, TNS −302.161 ns, 590 failing
setup endpoints, versus parent −1.399 / −250.635 / 446. All 8452 nets route;
hold +0.071 ns and pulse +1.830 ns pass. Use is 2729 LUT / 5788 FF / 21 DSP /
15 RAMB18. Reset structure checks pass; CDC remains nine CDC-3 and 208 CDC-15
items, with no waivers. OOC inputs/outputs remain unqualified (114/124).

Vivado replicated the release register. Querying only the original register
finds no old endpoint paths, but the replica still drives them. Replica-aware
queries show release→fast-fault −0.774 ns (parent −1.324), release→ROM-valid
−0.867 ns and release→output-request −0.616 ns. Global worst is now
release-replica→kernel protocol-fault, twelve logic levels, 7.096 ns data delay,
71.7% routing, through a 2160-fanout running net and the READY→guard→input-accept
chain. This candidate is not promoted despite its passing functional evidence.

Next test removing the two newly introduced KEEP hints on parallel capacity
and input-room expressions, with exactly unchanged behavior and constraints.
Those hints can prevent logic absorption; whether removal helps is unproven
until matched synthesis/routing. If the deep READY→guard→protocol-check chain
persists, investigate that control boundary rather than removing more TX or
relaxing publication/reset safety. Preserve this routed reference for comparison.

Use the unchanged 100/175 MHz diagnostic clocks and route recipe. Inspect the
exact old release-to-fault/request/ROM paths and retain full timing/CDC reports.
A local path improvement is not full timing closure; no timing exceptions or
clock changes are introduced here.

Full receiver timing/CDC/reset/real board clocks, 60 MS/s RX calibration,
continuous RX, sustained Ethernet/IIO, blind GLRT comparison and 120 ms/300 s
scan verification remain required before a pinned PPU/rollback package goes to
`.18`, followed by `.17` Ethernet-only verification. `.20/.21` remain excluded.
No radio, PPU/main or primary HDL change is part of this experiment.
