# Private inverse ACK retirement: improved route, still not timing-closed

FW `a4b1e3dea` / HDL `470eae191` are preserved on
`codex/starlink-rx-only-do-not-merge-private-ack-retirement`, based on held handoff
(`563614b87` / `576eb8897`). No radio, PPU/main or primary production HDL changes.
Production gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implementation and verification

Inverse-only, default-off private ACK retirement can clear private occupancy
when readiness coincides with a known idle fault. The same edge latches that
fault into sticky quarantine. Public ACK/admission/publication and diagnostics
remain unchanged; X/Z conditions retain original hold behavior. Incompatible
substituted phase-fault accounting is rejected. Internal awaiting/busy state may
differ only after known quarantine; this is not a public release or early reuse.

Whole top/guard inverses check the limited change. A 128-case transition test
permits exactly one known-fault difference, preserving unknown/default behavior.
The actual inactive guard's seven fault/event inputs are tested in 16,384
four-state combinations: idle fault equals the full fault OR. Incorrect private
updates, omitted external accounting and incompatible mode are rejected.
**514 combined tests pass in 74.65 seconds.**

The actual FFT bench compares a real guard using the original ACK update over
501,911 cycles: public ACK, admission, data, validity, active state and full fault
reasons match. All 306 private occupancy differences occur with both protocol
faults known one and public ACK/admission zero. Six new tests target actual
reader readiness: vendor fault, orphan output/status, both resets and healthy
release. They preserve current-edge release veto, block stale reuse and recover
with 512 correct reads and one release. The reader had already consumed its
original data before ACK-edge injection; those reads are not retroactively
cancelled. Prior bank/ownership/fault/reset tests also pass.

All **64,512 actual generated-FFT records** and the CSV remain unchanged.
Service: 3659/3659/4927/11727/3659/3659 clocks; the 11727-clock case includes a
deliberate 9000-clock reader pause. It is excluded from the 5215-clock diagnostic
service bound. The longer overall bench timeout accommodates added recovery
tests; physical clocks and per-context service limits are unchanged.

## Physical comparison

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |
| Held handoff parent | -1.868 ns | -565.807 ns | 720 |
| Private inverse ACK | -1.617 ns | -488.478 ns | 679 |

Improves all three metrics over its parent. Compared with private certification,
25 fewer endpoints fail, but WNS is 0.165 ns worse and TNS 37.310 ns worse.
**Retain both; no overall best-reference, timing-pass or deployment claim.**
679/13797 setup endpoints fail. Hold +0.057 ns, pulse +1.830 ns; 8340 nets fully
routed with zero errors. Resources: 2771 LUT / 5666 FF / 21 DSP / 15 RAMB18,
zero RAMB36. Unchanged 100/175 MHz diagnostic clocks, no new waivers. Five
critical CDC findings, 208 warnings, 114/124 unconstrained board I/O remain.

Worst path now reaches inverse input-count bit 7 from scheduler phase through
input metadata/checker and delivery qualification: eight levels, 7.276 ns data
delay, 5.828 ns routing. The next path (-1.577 ns) reaches another count bit.

## Next gate and deployment path

Inspect whether a prequalification offer can advance only private input-count/
completion observations, with same-edge full fault accounting quarantining any
difference. Do not claim private offers were delivered or weaken public valid,
final qualification, diagnostics, reset or ownership. Compare healthy/unknown
and fault-edge behavior against the original guard, then rerun actual FFT and
unchanged routing against this candidate and the private-certification reference.

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s calibration and Ethernet/IIO qualification precede `.18`
reversible canary, then `.17` PPU Ethernet-only deployment with pinned rollback.
Final gate: 300-second scan, 120 ms valid dwells and blind host GLRT comparison.
No deployment date is established by this result.

## Evidence

[Read-back verified archive](20260911-staged-privateack-evidence.tgz),
[receipt](20260911-staged-privateack-evidence.json): 15,970,448 bytes,
7,568 members; SHA256
`39ead943e5d5ca03d940823c4136e57c30fdc4f5bd08dbded7682d7ac773eef2`.
Actual / synthesis / route: 211.39 / 96.13 / 67.19 seconds, first attempts.
Source/checkpoint/report audit passes; physical timing gate fails.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-ack-retirement-worktree-v1`.
Sibling artifacts: `staged-privateack-{prepared,actual,synth,route}-v1`.
Inventory `201ab2965aa0f271643d4302af0467359ba50b65ef8249a862ab519bb3ef55a8`;
synthesis DCP `016f61a95632d0b7859145d8687ff9e6e3c29ab7e3077651d0644b5ff499454b`;
routed DCP `58ae66aa8d7bbed4c137c493f32b6b8b52a032d3b24060e7e48a4a67a536d45b`.
