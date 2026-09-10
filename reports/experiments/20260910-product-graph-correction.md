# Correction: staged-product graph audit omitted connections

**The earlier3123-node/zero-cycle claim is withdrawn.** The original848-test
run still has its recorded PASS outcome, but its graph test was a false
negative and does not establish acyclicity or its claimed cone exclusions.
No prototype/top was physically qualified or deployed on this basis.

While building the additive interface tests, the implementation owner found
that the old parser accepted `L_`/`v` labels but omitted Icarus `LS_`
concatenation subnodes and repeated numeric suffix coordinates. Parent
independently reproduced this on the complete saved original87683 netlist,
SHA `034eebc7bf351336e7bae74b7ff7424ac67a04c35914b441b5cc635582e1d270`.
The old traversal reports3123 nodes and no cycle. The corrected traversal
includes3159 nodes, with36 additionalLS nodes, and finds a structural cycle:

`guard.fault_now -> current_faults -> direct_clean -> handoff_valid ->
destination_ready/mailbox_input_ready -> guard.slot_error -> guard.fault_now`.

The graph follows dependencies in reverse when discovering the path; the
above list is the signal-flow direction. The actual cycle labels and their
source aliases are retained in the parent JSON. Phase-exclusive behavior may
allow simulations to settle; it does not justify a whole-graph acyclicity
claim. This is a structural connectivity finding, not a measurement of
oscillation, mapped timing or receiver behavior.

## Independent reproduction and regression checks

Parent's read-only audit uses complete `LS?_0x`/`v0x` tokens with repeated
numeric suffixes, an operation allowlist, known procedural state/input cuts,
and rejection of unresolved references. It reproduces both the old false
negative and the new cycle without recompiling or changing the netlist.
Four executable checks cover a cycle routed only through a multi-suffixLS
node, the old parser missing it, an acyclic specimen and a missing-node error.

The first parent audit failed while reproducing the old node count because
full-line matching missed valid VVP statements with trailing driver comments.
It is preserved unchanged. The second uses statement-prefix matching as the
original did, retaining all new completeness requirements, and passes.
Neither attempt executes a simulation or vendor command.

Recovery `product-graph-parent.i0Uyyjei`; archive
`20260910-product-graph-parent.tgz`:2898 bytes, SHA
`8cb52060020f4e6da49c1e820b98f7c4e67d980216654536e8f887c7ae39b6cc`.
Includes both audit scripts, failed-attempt receipt and final cycle evidence;
tar comparison exited0. The original netlist is already preserved in the
parent848 archive linked from the preceding report.

## Required repair and independent design findings

The additive fixture must separate independent raw faults from acceptance-
dependent faults. Re-run complete behavioral tests and the corrected graph;
do not register away current raw-event publication vetoes to remove a loop.
The original848 sources and failure history stay intact.

The independent source audit also identifies three integration backedges:

- Invalid admission depends on job_accept/job_ready; feeding it straight back
  into current admission faults creates a loop.
- Invalid completion depends on return_commit_valid; feeding it back into
  that commit's current fault predicate creates another loop.
- Certified input events depend on reader core VALID. Feeding those into a
  shared reader-valid fault input—even through a phase-qualified producer
  predicate—can close another structural loop.

Keep acceptance diagnostics separately observable and preserve independent
raw/vendor/duplicate/current-token checks at the correct public boundaries.
Exact guard ACK and a persistent health-qualified scheduler receipt remain
required. Do not mistake a permitted private state advance on a new fault for
an escaped public ACK/admission; original registered quarantine semantics stay
in force. Independent controller lease/descriptor capture must precede inverse
discovery, not compare two aliases of the discovered head.

Parent fully read the158-line independent audit in the inverse branch,
`docs/starlink-product-sealed-p1-independent-audit-20260910.md`, SHA
`d178bae0691ec8bc74bce4ac7db0609e4d29a94b2e300e4360c7fe335b11de68`.
Its initial follow-up finds that the final inverse-sealed graph helper already
handlesLS/repeated suffixes and unresolved references; other prior claims are
being checked separately. No blanket invalidation of numerical or actual FFT
results follows from this product-fixture parser defect.

The separate retained-output scripted composition also caught a repeated
producer-closure receipt before any vendor run. Its owner is retaining the
failed attempt and implementing a once-only scheduler receipt. No complete
composition or measured eight-cycle dispatch pass is claimed yet.

No radio/PPU/production/main/clock/threshold change. Full receiver routing,
timing/CDC/IO, actual60 calibration, causal native fine/coarse15/pilot2.5 IIO,
120ms/300s scanning and `.18` then `.17` deployment remain incomplete.
