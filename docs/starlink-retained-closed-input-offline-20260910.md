# Closed-input cutover view: bounded offline candidate

This separate `retained_output_closed_candidate` directory adds a default-off
closed-input view to the independently preserved private-offer candidate.
Modes 00, 10, 01 and 11 are tested separately. No original qualified runtime,
baseline guard, actual bundle, numerical vector or clock file was edited.
All 80 source files of the qualified v5 bundle were rehashed unchanged.

Four runtime copies add no registers: wrapper/top parameter forwarding,
cutover parallel combinational observation and a guard visibility rule.
The new cutover output is the literal full current-fault predicate with only
`input_beat` and `input_complete` replaced by zero. The full `fault_now`, complete
sticky reason recurrence, admission/configuration and cutover state remain
literal. The new output is selected only for the completed-return fault branch.

In enabled mode, the three public return paths require
`completed_input_certified === 1'b1`: ordinary mailbox retirement, final mailbox
commit and forward retirement. This is an explicit fail-closed X/Z tightening,
not four-state equivalence. The original logical condition remains the default.
Private return storage is unchanged and never constitutes publication authority.
No completion predicate was added to guard ACK, forward handoff, controller
completion acceptance or real retained-reader release: an old inverse ACK may
legitimately occur while the new forward's input is incomplete.

## Executed proof and its limits

Owner original77849: **39 PASS / 5.89 s**, with all eight source-before hashes
unchanged afterward. Replay:
`python -B -m pytest tests/test_starlink_retained_closed_input.py -q
-p no:cacheprovider --basetemp=<unique-non-tmp-directory>/cases`.
Raw evidence is `retained-closed-input-tests-v2.gu0WbmpG` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

- Literal source-expression comparison: 8192 binary predicate-state/control
  valuations plus 212992 single-X/Z substitutions, 221184 executions. Repeated
  tuples are possible; this is not the full four-state Cartesian space or a
  protocol-reachability claim. Parent separately tested real old/new modules
  over the same count and rejected three dropped-term mutants.
- Real unchanged input guard: all 512 delivered beats checked before each edge,
  final edge has old complete0/current strobe1, and its settled output has
  complete1/strobes0. Then 255 known/X/Z perturbation probes remain closed;
  duplicate-start remains a direct veto and reset clears the epoch. No internal
  state forcing or core model is used for this premise.
- Real guard states are reached by input/raw handshakes: 16 nonfinal/final
  visibility specimens, eight known-certificate equivalences, four original
  X→0 tightened results and four preserved naive 0→X counterexamples. Twelve
  current raw/fault probes retain public equivalence; full diagnostic latching
  and reset remain equal. Real ACK works with shared completed-input0.
- Twelve full three-block compositions: four opt-in combinations × three
  reader profiles. Every run retains the literal original arithmetic,
  retirement and two-guard shadows, including invalid metadata comparisons.
  Each checks five 1536-word streams, six admissions, six final-input edges,
  six real ACKs and 7803 settled closed-input samples. A separate witness checks
  full cutover fault versus the restricted output whenever completion is known1.
  Dispatch remains eight scripted clocks. Declared state remains 2480 bits and
  three payload arrays; this is not a mapped FF or actual-core timing result.
- Executed missing-known-one, wrongly-completion-gated ACK and unclosed-input-slot
  mutants fail their dedicated assertions. Strict whole-source inverses reject
  missing/duplicate/unrelated edits and preserve default parameter/guard bodies.

The initial run1627f8 is retained as **20 PASS / 16 compile FAIL / 0.56 s** in
`retained-closed-input-tests-v1.Qiqlxp0W`. The new appended witness used the old
bench's already-undefined macro. Replacing only those new witness references
with literal hierarchy fixed compilation; no runtime equation was corrected.

## Source identity and residual qualification

Closed runtime hashes: cutover `6f3a4217…`, wrapper `62f7941b…`, top `1d01972d…`,
guard `53c336df…`. Inverse JSON `df227b48…` restores the complete private-only
files and the unchanged original cutover; the prior inverse then restores the
four qualified originals. Existing private-only publication remains separate:
FW1734ddbf23591150257d7defb320ac1eb0696996 / HDL75fa090855e872ec1fd56877af218a5900882429.

No vendor, route, radio or production gitlink changes were made. The earlier
same-domain timing failure remains unresolved until separately approved physical
measurement. Old full-predicate diagnostics must remain independently witnessed
in any later actual campaign; a shadow fed only the reduced predicate cannot
establish that equality. This gate is neither all prior415 fault cases on the
candidate nor the seven-context actual FFT qualification, continuous15/60 rate
proof, arbitrary stalled service capacity or lower-clock approval. New ports
and parameters support the source-bound named instantiations, not a general
positional-port ABI compatibility claim.
