# Retained logger: isolated simulator reproduction

Parent-owned original22575 completed the twelve-case standalone XSim experiment
with tool terminal0 at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-logger-repro-parent.u30ykGsn`.
All sources remained unchanged. This was a logger-only simulation, without FFT,
DUT, clocks, arithmetic or runtime qualification.

Cases2/3/8/9 (conditional-string arguments, input/raw families and both phase
values) each produced the same kernel exceptional condition and only131CSVbytes.
Their simulator processes returned0 despite the crash; the missing completion
marker and partial bytes classify all four as failures. The eight literal or
explicit-if/else cases completed with exact expected two-row CSV bytes. They
use the same automatic task, `$fdisplay` format and numeric arguments. This
supports replacing only the two conditional-string call sites in the main
witness with explicit if/else literal calls, subject to a separately frozen
whole-source inverse and full CSV-equality gate.

Reproducer SHA256:
`2d76d74eb8012c8b4d627aadb8beeaf068e31c61085e80a131ab1fe69571e5f6`.
The source task body byte-matches the original witness. This lane's Icarus
fixture gate was13PASS0.09s (tool chunk017047), retained in
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-logger-offline.KDnjoVLt`.
Icarus accepted all twelve forms; that result alone could not expose the
XSim-specific crash. No vendor process was launched by this lane.

Parent additionally preserved a parser-only counterexample in the actual probe
directory: a complete original v3 scripted log/77,953 numerical rows accepted
an appended `FATAL_ERROR:` marker because the prior regex treated underscore
as a word character. An ordinary `Fatal:` was rejected. The earlier actual
crash had already been rejected by its incomplete numerical/terminal inventory;
no previous actual PASS is relabeled. The proposed separate package adds only
explicit case-insensitive `fatal_error` rejection and exact negative controls.

Portable packaging preserves every regular file from the terminal minimal
vendor experiment and offline fixture tests, with complete SHA/length receipts.
The original raw parent artifacts, crashes, partial CSVs and accepted parser
counterexample remain intact. Packaging is separate tooling, not an additional
vendor or test campaign. DNM publication of this reproducer/evidence is expressly
authorized; no receiver/primary-runtime promotion follows.
