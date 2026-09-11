# Preflight versus publication: source-bound ordering evidence

FW `a2ca89ae7611520df4761899d6ace371f9e1683b` and HDL
`ba8bfdf2144f802e4baf10c0062d832c0567c1b7` are preserved on
`codex/starlink-rx-only-do-not-merge-preflight-publication-proof`. Parent is
guard facts (`bf817a6bd` / `82be254db`), not the regressing bank-local candidate.
All 17 runtime modules remain byte-identical to the retained parent. The HDL
change is testbench only. No radio, PPU, main or primary production HDL change;
production gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Finding

The inverse producer's completion receipt follows actual bank publication,
not private completion. New preflight did not overlap unpublished inverse
replay in the source-bound actual FFT tests. It did overlap an already
published bank awaiting its slow reader. That distinction matters when
shortening the shared preflight/fault/publication path.

Source ordering: the top sets `producer_transfer_receipt` only on
`output_published_valid`; inverse completion request requires that token;
the scheduler leaves ACK_DRAIN on its clocked completion receipt. The adapter
emits publication notification only after observing the real bank request
transition. Reader release is later, and is not the producer-close condition.

## Verification and limits

**479 tests pass in 69.85 s**, no failures/errors/skips. Runtime-preservation
checks compare all 17 prepared modules to the parent. A small abstract ownership
graph admits arbitrary stalls, reset and early token consumption after actual
publication. It has no preflight/unpublished overlap and does have preflight/
unread overlap. Two unsafe graphs, using private completion as a receipt or
allowing ungated close, produce counterexamples before any actual publication.
This graph is not formal verification of the RTL; source contracts and actual
FFT/bank tests supply separate evidence. Yosys/SymbiYosys were not found on PATH.

The actual generated FFT run passes on its first attempt in 169.63 s. All
64512 numerical rows and CSV remain exact; service stays
3659/3659/4927/11727/3659/3659 clocks. The deliberately stalled reader contributes
9000 clocks to the 11727-clock context, excluded from the unchanged 5215-clock
diagnostic service bound. The overall simulation deadline is unchanged too.

Three new cases pause both private replay consumption and actual publication
authorization, queue the entire next source block, and hold for an additional
128 clocks. Total observed pauses are 1025, 1024 and 1024 clocks. No preflight,
producer-transfer receipt, completion request/permit or publication notification
occurs while paused.

1. Resume: observe forward preflight while the old bank is published/unread,
   then drain 512 correct old words and observe real release.
2. Resume and corrupt new preflight framing: observe the original current fault,
   sticky quarantine and no new publication or stale reuse. The previous
   publication is not retroactively cancelled; no old reads occurred while the
   reader was held stopped.
3. Fast reset while still paused: assert reset before releasing either pause,
   so cancellation cannot race publication; both domains stop exposing work.

All three then reset and recover with 512 correct fresh reads and one actual
reader release. Across 419084 live phase observations, all 3122 replay
observations have both full and contextual preflight events known zero; 62
preflight observations overlap published/unread ownership. These are cycle
observations, not frame counts or all-state formal coverage. Existing numerical,
fault/reset, certificate and reader-stall checks remain active. 150 admission
and 103 completion receipts include aborted work. Eleven new evidence-auditor
controls reject incomplete pauses, missing phase coverage and short recovery.

## Next implementation gate

Investigate a publication-specific current fault summary that excludes only
the current preflight terms shown zero during live replay. Retain registered
preflight faults, all other current fault vetoes, diagnostics, reset and actual
reader release. Do not apply an exemption to the published/unread state.
Compare the proposed publication authorization to the original on every tested
edge, retaining the new queued-pause and preflight-fault cases.

Separately investigate registering fault components before aggregation to
shorten preflight-to-sticky-fault timing without delaying the visible fault
edge or changing four-state behavior. Check the resulting CDC path: an OR moved
after registers must not silently introduce an unqualified crossing.
Neither runtime change is implemented by this verification-only experiment.

After implementation: source-level equivalence arguments, hostile boundary
tests, actual FFT, unchanged route and CDC review. The retained guard-fact
default route still fails at -1.340 ns WNS / -463.636 ns TNS / 821 endpoints;
its post-route physical variant also fails. No new route or timing pass is
claimed here, and reports in the archive are labelled inherited.

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s RX calibration and Ethernet/IIO qualification precede
`.18` reversible canary, then `.17` Ethernet-only PPU deployment with rollback.
Final gate remains the 300-second scan, 120 ms valid dwells and blind host GLRT.
No continuous receiver or deployment claim.

## Evidence

[Verified archive](20260911-staged-preflightpublication-evidence.tgz) and
[receipt](20260911-staged-preflightpublication-evidence.json): 16012774 bytes,
7452 members, all read-back verified. SHA256:
`7705b1ba92841c9c0e6135b910b5aa0bf9b5a7e064e84d81558e3612d0806bf5`.
Includes new bench/prepared sources, actual FFT log/CSV, tests and inherited
parent synthesis/route evidence. Packager rechecks all 17 runtime modules.
Prepared inventory:
`8c8206d52ab29723d585c44c52a87dce8ec87452ec566b83e98b33a3c67ac0f3`.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/preflight-publication-proof-worktree-v1`.
Sibling artifacts: `staged-preflightpublication-{prepared,actual,unit,regression}-v1`.
