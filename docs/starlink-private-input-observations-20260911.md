# Private inverse input observations — isolated experiment, DO NOT MERGE

Parent FW `a4b1e3dea` / HDL `470eae191`: private ACK retirement, -1.617 ns WNS /
-488.478 ns TNS / 679 failing endpoints. Compare also private certification
(-1.452 / -451.168 / 704) and guard facts (-1.340 / -463.636 / 821). No candidate
has timing closure or deployment qualification.

## Limited runtime change and safety contract

Default-off `PRIVATE_INPUT_OBSERVATIONS` opts in only the inverse guard under
certified admission. Its private input count and completion observation can use
the metadata-independent offer `guard_valid && transport_ready` and offered
last. It does not change the input checker, actual core-input valid, delivered
certificates, fault accounting, final qualification or public output/ACK gates.

The caller supplies the actual input-checker fault. When it is known zero,
offers must equal certificates; when known one, the same current fault must
appear in the guard's external fault accounting. A private count/completion
difference is permitted only after known sticky quarantine closes publication
and reuse. Unknown checker fault selects the original certified observation.
A private offer is not evidence of certified delivery to the FFT.

Complete top/guard source inverses check the delta. The prior ACK source inverse
uses its SHA-pinned parent; current ACK transition/accounting tests remain live.
The actual original-input-observation guard witness already compares all public
and diagnostic outputs. New checks compare its count/completion state with the
candidate, allowing a difference only when both protocol faults are known one
and publication/admission/ACK are known zero. Every known-zero checker fault
must also make the two offered events case-equal to the two certificates.

Five added inverse-input cases at a matching 32-word prefix: wrong position,
wrong metadata, premature last, duplicate start and unknown metadata. Known
fault cases must show private count 33 versus original 32, with immediate known
quarantine; premature last must exercise completion-state divergence too.
Unknown metadata must retain the original counter state. After cancellation,
require no stale publication/reuse and fresh 512-word/one-release recovery.

## Frozen gates and initial verification

37 unit/preflight tests pass in 10.77 seconds. Nine focused tests pass in
0.73 seconds after adding checker coverage (six overlap the initial run).
Observation selection: 2,048 four-state cases and four rejected bad expressions.
The real input checker is tested over 196,608 combinations of slot phase,
expected ordinal, valid/enable/ready/start, metadata, position and last, including
unknowns. In all 68,304 known-zero-fault cases, offers equal certificates exactly.
Ignoring eligibility or using the wrong completion offer is rejected. This
finite combinational check is not a formal proof of the complete receiver.

Require all 64,512 actual FFT records and six service intervals unchanged,
original guard public/diagnostic equivalence, known quarantine on every private
difference, exact unknown fallback, complete regressions and source-matched
synthesis/route at unchanged 100/175 MHz diagnostic clocks. Do not weaken the
physical or service gates or add receiver features before closure.

Prepared inventory: `d82c3f53c99f6126c4e9e77625b0bc02aa46e68b00c71ab87695dbe3e4782d27`.
Actual FFT passes in 218.19 seconds; source-matched synthesis in 95.43 seconds,
both first attempts. All 64,512 numerical records match with byte-identical CSV
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service remains 3659/3659/4927/11727/3659/3659 clocks. The 11727-clock context
includes a deliberate 9000-clock reader stall, excluded from the 5215-clock
diagnostic service bound; no timing or throughput limit was relaxed.

The private input monitor passes 543,731 cycles and observes 424 cycles of
private count/completion divergence, all under known sticky quarantine. The
original guard's public/diagnostic comparison remains active and passes through
the new cases. All five malformed/unknown cases recover with 512 correct reads
and one real release. The unknown case preserves original observation state.
The original bank witness also passes 543,730 falling-edge writer-state checks;
its 80 first-word, 200 final-word, 120 replay, 27,638 valid/ready reader and
21,960 stalled-reader counts are observations, not unique published frames.
201 admission and 146 completion receipts include aborted work.

Synthesis DCP: `8402a1c159f6c21c6cc7bfd177bf92d4edbec90685ffd26fa596738aacd4952c`.
Full regression: **533 passed**, no failures/errors/skips, in 74.982 seconds.
Route completed in 57.80 seconds on its first attempt; source/checkpoint audit
passes, but the physical timing gate fails. Routed DCP:
`5f2b10393760c7353703c921e3c367783e15c1587910e6c72d78932c5f304b0d`.

## Physical result: retain experiment, do not promote

WNS **-1.645 ns**, TNS **-607.093 ns**, **1011/13745** failing setup endpoints
at unchanged 100/175 MHz diagnostic clocks. Relative to private ACK parent,
WNS worsens 0.028 ns, TNS worsens 118.615 ns, and 332 more endpoints fail.
The intended private-count simplification is functionally validated, but is
not a timing improvement. Keep private-certification and guard-fact references;
do not stack further changes on the assumption this candidate is superior.

Hold +0.070 ns and pulse +1.830 ns pass; 8267 nets fully routed, zero routing
errors. Resources: 2703 LUT, 5646 FF, 21 DSP, 15 RAMB18, zero RAMB36.
Five critical CDC findings, 208 warnings and 114/124 unconstrained input/output
ports remain: this is an isolated diagnostic build, not board signoff.

The worst path is epoch fast-release -> reset/core release -> input and guard
fault checks -> output-bank request toggle: eight logic levels, 7.307 ns data
delay, 5.859 ns (80.2%) routing. The next reported path (-1.619 ns) reaches
inverse guard fault diagnostics from held product metadata. Removing the
private count dependency has not removed the shared control/fault network.

Next, inspect reset release and publication authorization as a complete
registered boundary on the retained reference. Any experiment must retain
immediate reset/fault cancellation, current-edge publication veto and real
reader release; registering a fault without an equivalent current veto is not
acceptable. Budget any extra cycles against the existing service gate. Prove
faults on each boundary edge, both-domain resets, stale work rejection and
healthy recovery before actual FFT simulation and unchanged routing. No clock
waivers, extra features or further TX removal are justified by this result.
No continuous RX, physical or deployment claim.

## Required end state remains unchanged

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC and full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s calibration and Ethernet/IIO qualification precede
`.18` reversible canary, then `.17` PPU Ethernet-only deployment with rollback.
Final gate: 300-second scan, 120 ms valid dwells and blind host GLRT comparison.
No radio, PPU, main or primary production HDL change. The new sparse HDL
worktree excludes historical evidence copies; no existing worktree was removed.
