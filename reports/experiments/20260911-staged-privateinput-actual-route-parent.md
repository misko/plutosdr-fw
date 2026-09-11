# Private inverse input observations: verified behavior, route regression

FW `4719eda44ad7cb2c6eafc7d490bbd59d1dfb032e` and HDL
`084dc0349f8c895628e109940ddb64c658ee957e` are preserved on
`codex/starlink-rx-only-do-not-merge-private-input-observations`, based on
private ACK retirement (`a4b1e3dea` / `470eae191`). No radio, PPU/main or primary
production HDL changes. Production gitlink remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implementation and tests

Inverse-only, default-off private input observations remove current metadata
qualification from private count/completion updates. Known-zero checker fault
requires offers equal certificates; known-one fault must be included in current
guard accounting and quarantine any divergence. Unknown fault retains original
certified observations. Actual FFT input delivery, public outputs, final
qualification, fault diagnostics and ACK remain unchanged. A private offer is
not proof of certified delivery.

Whole top/guard source inverses validate the limited delta. Selection covers
2048 four-state cases and rejects four bad expressions. The real input checker
is exercised over 196608 combinations; all 68304 known-zero-fault cases have
case-exact offer/certificate equality. Two incorrect offer definitions fail.
This finite combinational premise check is not a complete receiver proof.

**533 tests pass**, no failures/errors/skips, in 74.982 seconds. Actual generated
FFT simulation passes all **64512 records**, with byte-identical CSV. Service
intervals remain 3659/3659/4927/11727/3659/3659 clocks. The 11727-clock context
includes a deliberate 9000-clock reader stall and is excluded from the existing
5215-clock service bound; no physical clock or service gate was relaxed.

The original inverse guard public/diagnostic witness remains active. New
private-state checks cover 543731 cycles; all 424 count/completion differences
have known sticky quarantine and no publication/admission/ACK. Wrong position,
metadata, premature last and duplicate start exercise known-fault divergence;
unknown metadata retains original observations. All five cases reject stale
work and recover after reset with 512 correct reads and one real release.
Original bank writer/reader, stall, reset and fault comparisons also pass.

## Route comparison

| Candidate | WNS (ns) | TNS (ns) | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 | -451.168 | 704 |
| Expanded guard facts | -1.340 | -463.636 | 821 |
| Private ACK parent | -1.617 | -488.478 | 679 |
| Private input experiment | -1.645 | -607.093 | 1011 |

**Not promoted:** all three metrics regress against its parent. The count
dependency was simplified, but the shared control/fault network still fails.
1011/13745 setup endpoints fail at unchanged 100/175 MHz diagnostic clocks.
Hold +0.070 ns and pulse +1.830 ns pass; 8267 fully routed nets, zero routing
errors. Resources: 2703 LUT / 5646 FF / 21 DSP / 15 RAMB18 / zero RAMB36.
Five critical CDC findings, 208 warnings and 114/124 unconstrained I/O remain.

Worst path: epoch fast-release -> reset/core release -> input and guard fault
checks -> output-bank request toggle. Eight logic levels, 7.307 ns data delay,
5.859 ns routing (80.2%). Next reported path (-1.619 ns) runs from held product
metadata into inverse guard fault diagnostics. This is not a TX-resource issue.

## Next boundary and deployment gates

Use retained reference candidates for the next experiment, not an assumption
that this change improves timing. Inspect reset release and publication
authorization together as a registered boundary. Preserve immediate reset/fault
cancellation, current-edge publication veto, real reader release and unknown
behavior. Registering a fault alone is not an acceptable fix. Budget extra
cycles; test faults on each boundary edge, both-domain resets, stale work and
fresh recovery before actual FFT simulation and unchanged routing.

Do not add receiver features before subsystem closure. Preserve native 60 MS/s
fine search and independent 2.5 MS/s CI16 IIO inspection. Subsystem timing/CDC,
full receiver route/reset/board I/O, sustained capture, actual 60 MS/s RX
calibration and Ethernet/IIO qualification precede `.18` reversible canary,
then `.17` PPU Ethernet-only deployment with pinned rollback. Final gate:
300-second scan, 120 ms valid dwells and blind host GLRT comparison. No full
receiver, continuous native RX, physical signoff or deployment claim.

## Evidence

[Verified archive](20260911-staged-privateinput-evidence.tgz) and
[receipt](20260911-staged-privateinput-evidence.json): 15975152 bytes,
7635 members, all read-back verified. SHA256:
`968bc435b6d045a5ef4f69923cff7d1dd7e3e09eb8dad462754e947d0aa3f448`.
Actual/synthesis/route: 218.19 / 95.43 / 57.80 seconds, first attempts.
Source/checkpoint/report audit passes; physical timing gate fails.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-input-observations-worktree-v1`.
Sibling artifacts: `staged-privateinput-{prepared,actual,synth,route}-v1`.
Inventory `d82c3f53c99f6126c4e9e77625b0bc02aa46e68b00c71ab87695dbe3e4782d27`;
synthesis DCP `8402a1c159f6c21c6cc7bfd177bf92d4edbec90685ffd26fa596738aacd4952c`;
routed DCP `5f2b10393760c7353703c921e3c367783e15c1587910e6c72d78932c5f304b0d`.
