# Frozen pre-evaluation destination-absorption experiment

Offline combinational proof only. No runtime, controller, observer, constraint,
vendor execution or existing reason-vector edit. The exact three source files
are SHA-bound to the immutable retained-summary synthesis input snapshot.

The original mailbox `input_ready = in_running && !input_fault && request_toggle == acknowledge_sync[1]`
is copied literally. The complete original retained-owner module is compiled,
including its unchanged current-fault, reusable, reservation, release and reason
recurrences. This experiment assigns its private Q values without clocking:
it proves algebra, NOT state reachability, reset recovery or actual ACK behavior.
Both original full common-fault expressions and the complete six-bit original
preflight reason vector are copied literally from the pinned top.

Candidate A is frozen as `next_inverse ? output_bank_ready : product_bank_ready`
for only the parallel summary destination term. The other five preflight bits,
all independent fault terms and detailed original reasons stay unchanged.
If `fast_running !== 1'b1`, the candidate is exactly the original aggregate.

Candidate B is declared separately BEFORE evaluating A: inverse destination is
`output_bank_ready && reserved_known`, where `reserved_known` is case-exact
knownness of the owner's PRIVATE `reserved` Q bit. This is an additional
observational seam not currently exported by the owner; it is not authorized
runtime implementation, and synthesis behavior of X tests is not presumed.
Outside known-one running it also uses the original aggregate. The proof must
show B either exactly equals the original or changes original X to known fault1;
original clean0 and known fault1 must be preserved. No weaker X-to-clean result.

Candidate C is the parent-preferred exact contextual variant, also frozen
before execution: select A's scalar aggregate ONLY when running is exactly1
AND private reserved is exactly0 or1; otherwise select the entire literal
original aggregate. Require unconditional case-exact equality, including
phaseX/Z and preparingX/Z. B is only a separately labeled analytical control;
C, not B, is the proposed next contextual expression. A future owner known-state
observation would require review; no owner state/release/reason changes are made.

The suspected unrestricted A counterexample (prediction, not a result yet) is
running1, ready1, reasons0/current0 and reservedX: old reservation may be X,
while replacing it with raw readiness yields clean0. Preserve the executed
witness if confirmed; do not relabel unrestricted A as passing. Separately test
A exact equality when reserved is binary while all other controls/state may
be X/Z. A source-specific inductive known-reserved argument remains a separate
integration obligation even if that restricted combinational proof succeeds.

Finite proof decomposition: enumerate98304 owner input/state combinations using
all four values for seven scalar inputs/Qs, both exact lease mismatch classes,
and all three reason-reduction values. Deduplicate ONLY the complete owner
output signature consumed by the summary, keeping a concrete input witness for
each. Enumerate all phase/preparing/product-ready/option values and all logical
values of independent other-preflight/other-current aggregates per signature.
The2916-case six-cause conditional/reduction lemma independently proves that
reduction of the other five bits is complete, including unknown conditionals.
Also enumerate all256 two-bit lease pairs and all65536 reason bit patterns;
exercise each27 independent fault roots in all four states paired with every
retained-reason bit/value and every summary option (13824 cases). Logical OR
associativity covers arbitrary simultaneous independent roots, not a claim of
unrestricted temporal composition. Original and offered aggregates share no
new source predicates; the original input-fault X-tightening remains literal.

No physical latency/area claim follows. A may offer zero-state combinational
absorption only in a proven context. B's additional knownness input and any
fallback mux may defeat the intended physical reduction; root review is needed
before choosing any RTL experiment.
