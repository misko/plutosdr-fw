# Same-edge forward final commit — DO NOT MERGE

The preceding route's slowest same-clock path was handoff validation through
fault/commit/ACK control. The forward guard's final-state updates still used
the unrestricted mailbox fault, including the inverse output mailbox's current
framing logic. The existing forward-retirement contract already excludes that
current framing term in a known forward phase, while retaining sticky mailbox
faults and every other current veto.

## Candidate

Use the same parallel forward-final predicate for the guard's internal final
handshake only when USE_FORWARD_RETIREMENT is enabled and inverse_phase is
known zero. Unknown phase, inverse phase and disabled callers retain the original
handshake. Public mailbox valid/commit, detailed diagnostics, final status and
exponent qualification, reset, readiness and sticky faults are unchanged. No
additional register, delayed certificate or cycle of latency is introduced.

Only one runtime module changes, plus an additive actual-FFT witness in the
bench. Exact inverse tests reconstruct the parent runtime and bench. Earlier
source-inverse tests normalize this explicit delta before checking their own
historical changes; their behavioral stimuli and reference results are retained.

## Gates

Four-state tests instantiate the actual guard and compare its selected final
handshake with the original public commit AND readiness expression. Each of
four enabled/disabled completed-input/forward configurations checks 65536
combinations, including unknown phase and qualification. Missing reset,
qualification, fault veto, wrong fallback and a caller violating the phase
contract are rejected. These are finite contract checks, not a formal proof
of the integrated caller.

Both actual generated-FFT campaigns therefore also compare the original and
new final handshake for BOTH owners throughout fault, stall, cancellation,
publication and fresh-recovery cases. A pre-route gate requires exactly one
complete witness with nonvacuous final accepts from each frozen campaign;
deleting, duplicating or weakening a marker is rejected. All inherited
numerical/service gates remain required. Runtime, bench, synthesis helper and
Tcl are frozen together before these runs.

Route the source-matched pair at unchanged 100/175 MHz diagnostic clocks.
Inspect the old handoff-exponent-to-ACK/active and position-to-active cones
alongside global timing, all clock pairs, reset structure and CDC. A removed
targeted path or a passing simulation does not establish physical closure.

## Measured result: targeted improvement, reject overall promotion

1002 regression tests and seven witness-gate tests pass (1009 distinct).
Main/auxiliary actual FFT runs take 202.44/189.44 seconds and preserve all 64512
CSV records and service clocks 3663/3663/4929/11729/3663/3663. Final-commit
witnesses check 503564/437625 observations with 98/84 actual forward accepts.
Synthesis takes 101.00 seconds and routing 49.52 seconds.

| Metric | READY-absorption parent | Forward final candidate |
| --- | ---: | ---: |
| Global WNS, ns | -1.245 | -1.331 |
| Same-domain WNS, ns | -1.046 | -1.189 |
| TNS, ns | -245.991 | -277.204 |
| Setup failures | 453 | 526 |
| LUT / FF | 2728 / 5790 | 2732 / 5798 |

Matched read-only queries of both routed checkpoints show handoff-to-ACK
improving -1.046 to -0.255 ns and product-position-to-active improving -1.045
to +0.152 ns. The exact handoff-to-active endpoint has no reported path from
any of the five exponent source registers, versus -0.520 ns before; this is
an endpoint observation, not a claim that every handoff control path vanished.
Handoff-to-fast-fault improves -0.966 to -0.555 ns.

The new same-clock worst starts at the actual FFT flushing register, through
input READY and fault accounting to fast_fault: seven logic levels, 6.851 ns
data delay, 78.7% routing. Global worst is held output metadata bit 4 crossing
175 to 100 MHz. 8480 nets route without errors; hold +0.057 ns and pulse
+1.830 ns pass. DSP/RAMB18 remain 21/15. Reset structure passes, CDC remains
nine CDC-3 / 208 CDC-15, and OOC 114/124 input/output ports remain unqualified.

The frozen candidate emits a noncritical declaration-order warning because
forward_final_fault is declared below its use. Both elaboration and synthesis
resolve the declared wire; the warning is retained in evidence, not hidden.
Move the declaration before use in any follow-on source revision and rerun its
matched gates; do not silently edit the already-measured snapshot.

Retain this isolated experiment and the better overall parent. Next investigate
the single global sticky-fault register's input cone: partition independent
fault capture at that existing register boundary, rather than adding latency
to current publication vetoes. First prove equivalence to the scalar latch
including reset, X/Z, simultaneous faults, sticky persistence and forced summary
inputs; retaining raw current-fault fencing is essential. The same-edge final
cut is useful evidence, but this overall regression is not a release candidate.

## Deployment remains gated

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required, followed by full receiver timing/CDC/real board clocks, actual 60 MS/s
RX calibration, continuous RX and sustained Ethernet/IIO. Blind GLRT comparison,
120 ms valid dwells and 300 s scanning must pass before pinned PPU/rollback
qualification on .18 then Ethernet-only .17. No radio access, PPU/main changes,
primary HDL gitlink changes, TX removal or timing exceptions are part of this
experiment. .20/.21 remain excluded.

Prepared evidence: /dev/shm/starlink-forward-final.VUVSznt1/prepared-v1
SHA256: cb90644fc6c252e7a941bc57ef3c32c87f3b7b59d51d3b94c547114bee68c16a.
