# Bank-local identity: independent premise and complete scripted replay PASS

The next additive candidate moves full70-bit comparisons before phase selection
in the live input guard and preflight comparison0. It addresses the held-phase
half of the latest top20 timing paths, not the epoch-release half. The last
measured route remains **-2.504ns**, failing. No vendor or physical evaluation
of this new candidate has been performed.

## Source review and scope

Frozen pre-evaluation source: FW`a2b86d09958d8acc1d501bcd21764f42765d1065`,
HDL`a430c1643f0a320445b1877d5821f723b12bf406`, in the high-rate60-paired DNM
worktree. These new candidate commits are local pending the broader test gate.
Three copied modules introduce default-off `BANK_LOCAL_IDENTITY_EQ`: wrapper,
top and actual input guard. Parent reviewed all diffs, recipe and strict whole
inverses to the three original source files. All116 actual-qualified sources
remain unchanged.

Each input bank compares against the guard's **own immutable descriptor**, not
an assumed equivalent scheduler descriptor. A known phase selects one scalar
comparison. For X/Z phase, the original selected-metadata comparison remains
the exact fallback. Top preflight uses the same approach against engine_metadata;
comparison1 against expected_product_metadata is unchanged apart from a wire
alias. No state/counter/certificate/current-fault, data/position/LAST, transport,
ACK or release equation changes. Declared new state and latency are zero;
this is not a mapped resource result.

The module-level premise is important: the original selected input_metadata is
the phase mux of the same two bank metadata ports. The actual top wiring supplies
this identity. Arbitrarily inconsistent standalone input ports are not an
unrestricted equivalence claim. The unknown-phase fallback preserves the old
selected-input expression rather than claiming mux and equality commute in
four-state logic.

## Independent comparison checks

Parent first exercises the real original balanced input guard with forced
descriptor values and16,384 combinational probes. Two-bit four-state patterns
are repeated across all70 bits; this is **not exhaustive arbitrary70-bit input
coverage or reachable clocked state**. The fallback agrees throughout. The naive
scalar mux disagrees in144 cases; a wrong-bank control disagrees in2672 known
phase cases. A concrete counterexample is source00, product11, descriptor01,
phaseX: original equalityX, naive scalar0, fallbackX.

Parent then compiles the actual new input-guard source alongside the unchanged
original, checking disabled and enabled modes with both balanced and legacy
equality. Each candidate mode passes32,768 comparisons across those two settings.
Eight source/recipe pins stay unchanged and all three source inverses pass.
Descriptor storage is deliberately forced for this algebra check; no clocked
job, reset recovery or buffer ownership claim follows.

## Complete original scripted numerical campaign

Root47932 terminal0: both mode0 and mode1 pass the complete original seven-context
scripted campaign. Only three compiled paths and one option/readback block change.
Readback checks wrapper, top and input guard. All old bench checks, numerical
vectors, guard/frame/reset/service references and result parser remain intact.

Both runs reproduce **all77,953 CSV rows byte-for-byte** and the entire prior
parsed result, including the offered-summary receipts. CSV SHA256:
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
All122 source/helper/recipe/vector pins remain unchanged. This campaign uses a
scripted FFT interface; it is not actual vendor FFT or routed timing evidence.
The new dedicated unconditional guard-state/adversarial suite is still pending.

## Next gates and parallel work

Complete clocked guard comparisons, both-bank/all-bit faults, phase transitions,
stalls, duplicate/delivery faults, resets, current-fault/real-ACK boundaries and
negative controls before actual vendor replay and physical evaluation.

Separately, the epoch-release path has a potential context-specific preparation
summary: retain original detailed reason capture but simplify destination
readiness only where independent owner/epoch facts justify it. Its four-state
aggregate proof is in progress; no readiness/ownership RTL change is accepted.
In particular, an unknown private reserved bit may defeat a naive simplification.
The previous write-token and proposed delayed-private-cleanup alternatives remain
deferred; neither addresses all currently measured paths.

Evidence under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `bank-identity-premise-parent.KdeMzGLX`: original guard, premise and counterexamples.
- `bank-identity-rtl-parent.evhFf4L6`: actual new/default guard checks and inverses.
- `bank-identity-script-parent.I6V7j9V0`: original complete scripted replay in both
  modes,122 source snapshots, commands, logs, CSV and complete result equality.

No radio/PPU operations, main merge, production gitlink or timing waiver occurred.
