# Publication-specific fault scope — isolated DO NOT MERGE candidate

Parent: preflight/publication ordering verification, FW
`a2ca89ae7611520df4761899d6ace371f9e1683b`, HDL
`ba8bfdf2144f802e4baf10c0062d832c0567c1b7`. Runtime is the guard-fact reference:
default route -1.340 ns WNS / -463.636 ns TNS / 821 failing endpoints.
Neither it nor its post-route physical variant is timing/deployment-qualified.

## Limited implementation and scope argument

Only actual output replay authorization changes. Under certified admission
and known replay-valid, use the offered current fault summary without current
preflight terms. Keep offered external faults, both guard-local current faults,
output-bank sticky/framing faults and sticky result faults. All diagnostic
accumulators, common current fault, reset, private replay handshake, reader
release and producer-publication ordering remain literal.

The excluded full/contextual preflight vectors are known zero whenever live
replay can authorize a write, as established by source ordering and the actual
queued-publication-pause tests. Published/unread banks are NOT exempted from
fault handling. Registered preflight faults still propagate through the unchanged
sticky reason/result/fast-fault paths. No added register, cycle or CDC change.

Default/non-certified mode and X/Z replay-valid use the exact original full
predicate. Zero replay-valid masks authorization independently of the private
summary. The reachable-phase premise is essential; this is not an algebraic
equivalence for arbitrary contradictory preflight/replay inputs.

## Frozen verification gates

Complete top source inverse permits only the new summary and changed final
authorization expression. The other 16 runtime files remain byte-identical.
Historical guard-fact inverses use the pinned parent; current predicate and
publication-order tests remain live. Four-state authorization comparison
exercises all six retained fault terms, descriptor/bank readiness, replay-valid,
default mode and unknown fallback. In certified live replay only, preflight is
required known zero. Four mutants must fail: lost external fault, lost sticky
result fault, dropped unknown fallback and dropped default-mode fallback.

Actual FFT continuously compares the new authorization to the original; live
replay must retain exact current fault equality. Keep queued publication pause,
published/unread preflight fault and reset tests. Add six replay-edge injections
at the retained summary terms, each requiring current veto, sticky quarantine,
no stale publication/reuse and fresh 512-read/one-release recovery. These are
summary-wiring injections, not six distinct raw hardware fault sources; existing
vendor, product framing and orphan status tests remain the raw-event controls.

Require all 64512 FFT records and service intervals unchanged, full regressions,
source-bound synthesis and the unchanged 100/175 MHz route. No weakened timing
constraints, service limit or simulation deadline. No receiver feature additions
before closure. **17 focused tests pass in 33.59 seconds**, including 1900544
four-state authorization cases and four rejected mutants. Prepared inventory:
`e39e5e7e9976065fa4c33f177816f543123bddb562c979d0c8741b67c3181ae1`.
V1 synthesis passes in 97.57 seconds, DCP
`fa2fdf75f70d263d97afe8395c9eed8accd3d99c7dcb9b9588a38bba07de28e1`.
V1 actual FFT runs 168.97 seconds: numerical and inherited fault/ordering cases
pass, but the first new injection triggers the existing scalar/partition
consistency assertion. Forcing `offered_external_fault_now` high left its
source-based admission facts low. Similarly, forcing only a reduced guard-local
bit would disagree with the expanded guard-fact vector. This is a contradictory
test injection, not evidence of a passing candidate. The original consistency
assertions are retained unchanged.

V2 changes only those test injections: use the raw vendor last-missing event
and each guard's shared summary vector before scalar/vector reduction. The
other three injections already feed both views. Runtime top and all other
compiled runtime modules are unchanged from V1. Preserve failed V1 evidence;
rerun actual FFT and source-matched synthesis with a fresh V2 inventory before
routing. No failed run is reclassified as a pass. A dedicated V2 source-inverse
test passes in 0.02 seconds: all 17 runtime files match V1 and the bench changes
only these injection/release sites; every consistency assertion remains literal.
V2 inventory:
`62cd6b63907f29dd5e40a9802cd2ca161b897589f0d9e0775eebb8879c5a30d1`.
V2 actual FFT passes in 191.24 seconds and synthesis in 95.98 seconds, both with
unchanged source receipts. All 64512 numerical records and CSV remain exact
(`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`).
Service remains 3659/3659/4927/11727/3659/3659 clocks; the deliberate 9000-clock
reader stall is included in the 11727-clock case, excluded from the unchanged
5215-clock service gate. No simulation or service deadline was extended.

Original authorization matches for 479822 falling-edge observations. All 3133
live replay observations retain exact current fault equality. All six new
retained-fault cases preserve current veto/quarantine and recover with 512
correct reads and one actual reader release. Queued-publication pauses,
published/unread preflight faults and resets still pass. Earlier phase receipt
reports 419084 checks/3122 replay/62 unread-preflight observations before the
six added cases; its monitor remains active afterward. These are observations,
not unique frames. 174 admission/121 completion receipts include aborted work.

V2 synthesis DCP:
`316639f158210201515dbb480b99af9d00bca970e831d565db01b8a0c5f5e1e6`.
Full regression: **496 tests pass in 93.983 seconds**, no failures, errors or
skips. Unchanged route completes in 53.54 seconds with source/checkpoint audit
passing and zero routing errors. Physical timing fails:

| Measurement | Guard-fact reference | Publication scope |
| --- | ---: | ---: |
| Worst setup slack (ns) | -1.340 | -1.888 |
| Total negative slack (ns) | -463.636 | -598.888 |
| Failing setup endpoints | 821 | 881 |
| LUTs | 2808 | 2725 |
| Flip-flops | 5691 | 5684 |

Both use 21 DSPs and 15 RAMB18s. New route has 8340 fully routed nets, hold
slack +0.062 ns with no hold failures, and pulse slack +1.830 ns. The reduced
logic utilization does not translate into improved timing. Do not promote this
candidate over the retained reference. Routed DCP SHA256:
`1df782ea68ba3064e323db04edfa6e1790fe09c6a4995561decf4fe91aa765c0`.

The worst same-domain path remains held phase to output-bank request-toggle D,
now via input metadata identity, input fault events and owner fault aggregation.
It has 11 logic levels and 7.597 ns data delay; 5.777 ns (76.0%) is routing.
Removing preflight terms from replay authorization did not break this surviving
combinational path. 114 unconstrained inputs and 124 unconstrained outputs
remain visible in this diagnostic OOC build; this is not board signoff.

## Next architectural gate

Keep the guard-fact/private-certification references. Before another runtime
candidate, specify a registered validation-to-publication boundary: identify
which payload and descriptor remain private, when validation finishes, which
faults veto on the current edge, and when real reader ownership starts. A
pending publication must be cancelled on fault/reset and must not permit reuse
until the existing ownership contract allows it. Adding a register to a shared
fault wire alone is not sufficient: that could permit a bad publication for
one cycle. Any replacement must demonstrate the same externally visible
quarantine and reset behavior, with explicit added service/buffering cost.

Test faults immediately before, on and after that boundary; held/unread output,
queued next input, arbitrary reader stalls and both-domain resets. Use the
actual FFT and RAM buffers, retain numerical comparison, then route the complete
subsystem with unchanged constraints before adding features. Do not silently
relax the 5215-clock budget or lower the clock. No new boundary implementation
or success is claimed here. Native fine search and inspection remain separate
preserved requirements, not features to remove for this control-path failure.

## Full end state remains required

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
untouched. Subsystem timing/CDC, full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO qualification
precede `.18` reversible canary, then `.17` PPU Ethernet-only deployment with
pinned rollback. Final gate remains the 300-second scan, 120 ms valid dwells and
blind host GLRT comparison. No radio, PPU/main or primary production HDL change.
