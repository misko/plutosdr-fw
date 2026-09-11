# Held bank metadata: numerical pass, timing regression — do not promote

FW `e25e9c5bf` / HDL `b41d5115b` are preserved on
`codex/starlink-rx-only-do-not-merge-held-bank-metadata`, based on expanded guard
facts (`bf817a6bd` / `82be254db`). No radio, PPU/main or primary production HDL
changes. Production gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implemented and verified

Registered scheduling uses the held inverse tag and guard exponent for private
bank writes and replay; nonregistered callers retain the original metadata mux.
No validity, commit, current fault, descriptor validation or reader-ACK predicate
changes. A whole-top inverse checks this limited delta. 1,184 four-state wiring
cases and three rejected mutations verify selection/fallback, not temporal
ownership. **479 combined tests pass in 70.41 seconds.**

A second real bank uses the original mux and observes identical live inputs.
It has no authority over candidate execution. Writer readiness, framing/sticky
faults, cursor, request/ACK and valid reader payload/metadata match through the
entire actual FFT, reset, fault and stall campaign. Counts: 385,028 writer-state,
53 first-word, 99 final-word, 46 replay, 16,374 valid/ready reader and 21,916
stalled-reader observations. These falling-edge observations are not unique
frame or continuous throughput counts. All **64,512 numerical records** match,
with byte-identical CSV and unchanged 3659/3659/4927/11727/3659/3659-clock service.
The 11727-clock context deliberately stalls its reader for 9000 clocks.

## Physical result

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |
| Held metadata | -2.203 ns | -672.268 ns | 796 |

The candidate saves 139 LUTs and five FFs versus its parent, but WNS worsens
0.863 ns and TNS worsens 208.632 ns. **Not promoted.** 796/13863 endpoints fail.
Resources: 2669 LUT / 5686 FF / 21 DSP / 15 RAMB18, zero RAMB36. Hold +0.072 ns,
pulse +1.830 ns; 8264 nets fully routed with zero errors. Source/checkpoint audit
passes, not physical signoff. Unchanged 100/175 MHz diagnostic constraints; no
new waivers. Five critical CDC findings, 208 warnings, 114/124 unconstrained I/O.

Worst path: output-control phase -> remaining private/replay selection and bank
framing -> inverse completion -> output-control phase. Thirteen levels,
7.862 ns data delay, including 5.414 ns routing. Next path (-2.086 ns) reaches
inverse guard fault reasons from registered scheduler phase.

## Next action and deployment gates

Examine the complete private-write/replay handoff: prove whether the retired
guard can supply all held payload/position/last values and whether private-valid
and replay-valid ownership are mutually exclusive. Do not assume those facts
from this metadata-only proof. Test late raw events, final/status/replay stalls,
both resets and real reader ACK. Retain immediate public fault vetoes; compare
actual original-bank/controller behavior and reroute before choosing a reference.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
required. Subsystem timing/CDC, full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s calibration and Ethernet/IIO qualification
precede `.18` reversible canary and `.17` PPU Ethernet-only deployment with
pinned rollback. Final gate: 300-second scan, 120 ms valid dwells and blind host
GLRT comparison. No deployment date is established by this result.

## Evidence

[Read-back verified archive](20260911-staged-heldmeta-evidence.tgz),
[receipt](20260911-staged-heldmeta-evidence.json): 15,750,597 bytes, 7,442 members;
SHA256 `099f9a4b6b07c1447ddfc71bcb90521288798e6942793d11cefcac46918c4b92`.
Actual / synthesis / route: 154.31 / 96.07 / 53.54 seconds, first attempts.
Packaging alone required two pre-archive corrections (campaign map and
indentation); no tested or routed source changed.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/held-bank-metadata-worktree-v1`.
Sibling artifacts: `staged-heldmeta-{prepared,actual,synth,route}-v1`.
Inventory `c26a6c00e91bfb2a484d91cfd9222ffdf3ead44ef51412530afab21e0ff3d878`;
synthesis DCP `afecf8050c27ddde9cd42d6057df1e0b56a9440a49b0cef5d481aad528ac5e33`;
routed DCP `24adc4a72cda88f9b5d1fdae69208eb538a15906643f0e603c2438cd933247fc`.
