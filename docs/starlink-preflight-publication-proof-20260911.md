# Preflight/publication ordering — isolated DO NOT MERGE verification

Use retained guard-fact runtime, not the regressing bank-local identity
experiment. FW parent `bf817a6bd3b1d0de948c0efe29b916a5850faf85`; HDL parent
`82be254db13c20eb5aed72cd2010138cf334dfe2`. All 17 compiled runtime modules
are byte-identical to the parent prepared source. Only the actual FFT testbench,
verification tools and evidence change. No new synthesis or route is needed to
measure a runtime change, because no runtime change is being claimed.

## Question and source reasoning

Can new preflight validation coincide with an old inverse block awaiting
publication? Distinguish this from an already published block awaiting reader
release. The top sets `producer_transfer_receipt` only on
`output_published_valid`, not private completion. Inverse completion request
requires that receipt. The adapter produces publication notification only after
the actual output-bank request transition; its private replay receipt alone is
not publication. The scheduler leaves inverse ACK_DRAIN only after the clocked
completion receipt. Reader release is later and does not gate that core reuse.

Hypothesis: a live inverse replay cannot coincide with preflight, but preflight
may coexist with a published/unread inverse bank. This needs reachable-phase
evidence, not an unconditional algebraic claim about arbitrary inputs.

## Tests and frozen gates

Six unit/lint tests pass in 0.08 s. They check all 17 runtime modules against
the parent, pin the top source, check the publication/close predicates and
exhaustively explore a small abstract ownership graph. The graph allows
arbitrary stalls, reset and early completion-token consumption after actual
publication, but cannot advance the inverse producer before publication. It
has no preflight/unpublished-replay overlap and does admit preflight/unread
overlap. Two deliberately unsafe graphs (private-completion receipt and
ungated close) produce counterexamples before any publication.

The graph is NOT RTL formal verification. Its abstract transition assumptions
still need the source contract and actual FFT/bank test. Yosys and SymbiYosys
were not found on PATH; this run does not claim formal signoff.

The actual FFT bench asserts during every live replay that `preparing`, full
preflight events and contextual preflight events are all known zero. Three new
cases pause inverse replay by holding both private consumption and actual
authorization low, queue an entire next source block, and hold for at least
128 additional clocks. Require no preflight, producer-transfer receipt,
completion request/permit or publication notification during this pause.

Case 0 resumes publication, observes next forward preflight while the old bank
is published and unread, then drains the real old reader. Case 1 resumes to the
same boundary and corrupts preflight framing: require the original current
fault, sticky quarantine and no new publication/reuse. Case 2 resets the fast
domain while replay is still paused, cancelling before either pause is removed.
Every case resets and recovers 512 correct reads with one actual release.

Require at least 1000 phase observations, 384 replay observations and two
published/unread preflight observations, all 64512 FFT records, unchanged service
intervals and all regression tests. No current fault gate is removed here.
Existing actual-FFT, guard-fact, certificate, fault, reset and reader-stall
checks remain. Overall simulator and service deadlines are unchanged.

Prepared inventory:
`8c8206d52ab29723d585c44c52a87dce8ec87452ec566b83e98b33a3c67ac0f3`.
Actual FFT passes on the first attempt in 169.63 seconds, with unchanged
source receipts. All 64512 numerical records and CSV match:
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service stays 3659/3659/4927/11727/3659/3659 clocks. The 11727-clock context
includes the deliberate 9000-clock reader stall and is excluded from the
unchanged 5215-clock diagnostic service bound.

All three new cases pass: pauses last 1025/1024/1024 observed clocks with the
next source block queued. No early preflight, producer close or publication
occurs. The complete bench observes 419084 live phases, including 3122 replay
observations with full/contextual preflight events known zero, and 62 preflight
observations overlapping a published/unread bank. These are cycle observations,
not unique frames or formal all-state coverage. Each case has fresh 512-read/
one-real-release recovery. The unread preflight fault retains original current
fault detection; the previously published request remains published, rather
than being retroactively cancelled. Both-domain cancellation follows fast reset
while publication is paused. 150 admission/103 completion receipts include
aborted work. **479 regression tests pass in 69.85 seconds**, no failures,
errors or skips. Eleven new actual-evidence auditor controls require all three
queued pauses, publication/unread coverage, exact-phase receipt and full fresh
recovery; weakened evidence is rejected.

The runtime-preservation test checks all 17 compiled modules against the parent
again during the regression, and the evidence packager repeats that check.
Synthesis/route reports in the archive are explicitly labelled inherited;
there is no new physical or timing-improvement claim.

## Next implementation decision and unchanged end state

If the phase evidence passes, investigate a publication-specific fault summary
that excludes only the current preflight terms already proved zero whenever
replay can authorize a bank write. Carry registered preflight faults forward;
do not exempt the published/unread state or change diagnostics, reset or real
reader release. Separately investigate registering fault components before
their aggregate to shorten the preflight-to-sticky-fault path while preserving
the exact externally visible sticky-fault edge and four-state behavior. Check
the resulting cross-domain fault path as well: moving an OR after registers
must not silently introduce an unqualified combinational CDC crossing.
These changes are not implemented or approved by a timing result in this run.

Both candidates still need source-level equivalence arguments, hostile boundary
tests, actual FFT and unchanged routing. The unchanged guard-fact default route
remains -1.340 ns WNS / -463.636 ns TNS / 821 failing endpoints; its separate
post-route physical variant also fails. No timing or deployment promotion.

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s RX calibration and Ethernet/IIO qualification precede
`.18` reversible canary, then `.17` PPU Ethernet-only deployment with rollback.
Final gate: 300-second scan, 120 ms valid dwells and blind host GLRT comparison.
No radio, PPU/main or primary production HDL change.
