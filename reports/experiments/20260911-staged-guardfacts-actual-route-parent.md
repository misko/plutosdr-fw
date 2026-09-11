# Expanded guard facts: exact certificates, mixed route result

FW `bf817a6bd` / HDL `82be254db` are preserved on
`codex/starlink-rx-only-do-not-merge-guard-facts`, based on private certification
(`eda2c6dce` / `cf4b70230`). No radio was flashed; no PPU/main changes.
Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implemented and tested

Export the same eight local fault facts from each guard before their OR
reduction. Admission and completion certificates register those facts separately
(22 to 36 and 28 to 42 bits). The scalar current-fault fence, snapshot/consume
protocol, quarantine, publication and real reader ACK remain unchanged.

Complete source inverses check the limited top/guard changes against pinned
parents. Source-extracted four-state predicates agree over 1,048,692 cases;
dropped facts, ignored disable and unknown-to-zero mutations are rejected.
**464 regression tests pass in 68.22 seconds**. This is not a formal proof of
the entire guard state machine.

**64,512 actual generated-FFT records match**, with byte-identical CSV and
unchanged six service intervals: 3659/3659/4927/11727/3659/3659 clocks.
The 11727-clock case deliberately stalls the reader for 9000 clocks; the
other contexts meet the 5215-clock diagnostic bound.

Original 22/28-bit certificate instances observe the same live requests and
quarantine but authorize nothing. Permits, stored facts, validity and consumed
state agree case-exactly for **384,922 cycles**. All **32 fact-mapping fault
injections** (two gates, two owners, eight facts) reject the snapshot and block
stale starts, reads and releases for 100 cycles. These injections prove fact
mapping/capture, not 32 distinct raw-source fault events. Prior actual-source
fault/reset/ownership campaigns also pass. Fresh reset/block recovery produces
512 correct reads and one real release. Ten new audit controls reject weakened
or incomplete evidence.

## Routed comparison

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification reference | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |

Worst slack improves by 0.112 ns, but total negative slack worsens by 12.468 ns
and 117 more endpoints fail. **Retain both candidates; no overall improvement,
timing pass or deployment promotion.** 821/13869 setup endpoints fail.
Hold +0.051 ns and pulse +1.830 ns pass. All 8465 nets route with zero errors.
Resources: 2808 LUT / 5691 FF / 21 DSP / 15 RAMB18, zero RAMB36.
Diagnostic clocks remain 100/175 MHz with unchanged recipe and no new waivers.
Five critical CDC findings, 208 warnings and 114/124 unconstrained board I/O
remain; routing completion does not mean timing or physical signoff.

Worst path: publication phase -> output metadata mux/comparison -> guard/current
fault checks -> output-bank request-toggle D. Eight levels, 7.051 ns data delay,
5.603 ns routing. Next path ends at inverse awaiting-ACK (-1.205 ns).

## Next gate and deployment path

Inspect whether output metadata can be prepared and held before publication,
removing phase-dependent selection from the wide comparison on that edge.
Prove exact first/final-word metadata, replay hold and fault/reset behavior.
Keep immediate public fault vetoes and real reader ACK; do not simply delay
fault detection. Compare actual FFT and source-matched route results against
both retained candidates before accepting a composition.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
required. Subsystem timing/CDC and full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO verification
precede `.18` reversible canary, then `.17` PPU Ethernet-only deployment with
pinned rollback. Final verification remains a 300-second scan, 120 ms valid
dwells and blind host GLRT comparison. No deployment date is established.

## Evidence

[Read-back verified archive](20260911-staged-guardfacts-evidence.tgz),
[receipt](20260911-staged-guardfacts-evidence.json): 15,851,868 bytes,
7,405 regular members. SHA256
`9a74f4fd9ae2d008c06f3b34f21fce7227d2f8808c93902b76b17b18de9fe9d6`.
Actual / synthesis / route: 156.56 / 96.69 / 60.47 seconds, first-attempt
successes. Source/checkpoint audits pass, physical timing gate fails.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/guard-facts-worktree-v1`.
Sibling artifacts: `staged-guardfacts-{prepared,actual,synth,route}-v1`.
Inventory `03bf519fbf39f8142e00861b7ac942b7e531afb07267a6965d89a88b977d5776`;
synthesis DCP `015edd7a3ff1d9472958657d068bd4115ea205362b6f88ef93321bc828e0a3c4`;
routed DCP `ab681d26848908f8a5454479611d14a74040ee00fafeff525f6b074ee71f287e`.
