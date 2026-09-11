# Private final capture: lower total timing deficit, closure still open

Implemented on private-capture reference FW `fcc3dc202` / HDL `c25126a2e`,
independently of the staged-final, ordinal and fault-summary regressions.
New FW `565dd5c45` and HDL `e200100db` are on
`codex/starlink-rx-only-do-not-merge-private-final-capture`.
No radio, PPU or main changes. Primary production HDL gitlink remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implemented and tested

The adapter's private final-data/tag/request bundle now tracks inputs while
its local registered phase is EMPTY. The original qualified completion
handshake captures those same inputs and transitions phase, freezing the
bundle through COMMIT, replay, publication, reader ACK and RELEASE. The
default-off feature is enabled only in the experimental FFT top. No clock
latency, public fault check, completion authorization or bank-ACK gate changes.
Invalid replay data/tag may churn while idle and grant no authority.

- **25 adapter tests pass**: twenty candidate/pinned-original comparisons
  with real dual-clock RAM, five cancellation positions, two stall lengths,
  enabled/disabled behavior, numeric/X/Z payload churn and fresh reset recovery;
  five unsafe capture variants are rejected.
- **64,512 actual FFT records match** the pinned reference; the CSV is
  byte-identical. Service remains 3659/3659/4927/11727/3659/3659 clocks. The
  deliberately stalled reader has no 5215-cycle claim; other contexts pass.
- The full earlier fault/reset/ownership campaign passes. Every accepted/held
  adapter bundle matches original qualified capture. Coverage: 196,225 loads,
  60,251 holds, 43 accepted completions and 1,171 fault-condition loads.
- **417 combined regression tests pass in 52.67 seconds**, including ten
  evidence-parser controls. Two preflight tests pass. Actual FFT / synthesis /
  route complete in 109.88 / 102.72 / 56.70 seconds on their first invocations.

## Physical result: mixed improvement, not deployable

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private-descriptor capture reference | -1.969 ns | -813.676 ns | 914 |
| Plus private final-data capture | -2.005 ns | -634.847 ns | 856 |

The aggregate deficit improves about 22%, with 58 fewer failing endpoints.
Worst slack is nevertheless 0.036 ns worse: retain both references, and do not
call this timing closure. 856/13801 setup endpoints fail. Hold +0.070 ns and
pulse +1.830 ns pass; 8412 nets fully route with zero errors. Resources:
2785 LUT / 5668 FF / 21 DSP / 15 RAMB18. Clocks remain diagnostic 100/175 MHz.
Five critical CDC findings, 208 warnings and 114/124 unqualified I/O remain.

The worst path now runs product block-start metadata -> bank identity check ->
shared fault/forward acceptance -> kernel expected-bin index enable. It has
ten levels, 7.430 ns data delay, 5.734 ns routing. The next path at -1.907 ns
feeds the kernel expected-next-block identity registers. Final-data capture
is no longer the reported worst endpoint.

## Next gate and deployment path

Address forward/kernel ordinal and next-block identity together. The previous
private-ordinal experiment alone routed worse; composing it with this capture
change is a bounded experiment, not an assumed improvement. Preserve public
per-bin/next-block validation, final qualification and fault/reset quarantine.
Alternatively partition the shared metadata/fault path with registered local
ownership. Compare WNS, TNS and endpoint counts against both retained references,
and require actual FFT plus fault/stall/reset proof before another promotion.

No new receiver features before subsystem timing/CDC qualification. Native
60 MS/s fine search and 2.5 MS/s CI16 inspection remain required. Full receiver
route/CDC/reset/board constraints, sustained capture, real 60 MS/s calibration
and Ethernet/IIO verification precede reversible `.18` canary and `.17` PPU
Ethernet-only deployment with rollback. Final verification remains 300 seconds,
120 ms valid dwells and blind host GLRT comparison. Deployment ETA remains
unproven while physical and full-receiver gates are open.

## Evidence

[Read-back verified archive](20260911-staged-finalcapture-evidence.tgz) and
[receipt](20260911-staged-finalcapture-evidence.json): 15,798,429 bytes,
7,405 regular members, SHA256
`133b25789d310c867da787e9363d96b06947080a255b1e20856c839eda6d3f98`.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-final-capture-worktree-v1`.
Sibling evidence: `staged-finalcapture-{prepared,actual,synth,route}-v1`.
Prepared inventory `49b2b174d13007264b6d4f6b9733a6f2930a7ecd8cff942d02ef9c8bd5496f44`;
synthesis DCP `21b12f88aaf6d6bce9cddd6a903411b279cfdc957ead0fa26c384494ab64e641`;
routed DCP `d0ad74cb1150d6ef75939e170d196eb72255316940abcd1d74cb4f3c5d61b1be`.
Independent route audit verifies source/checkpoint identity and report consistency;
it explicitly rejects physical-signoff and deployment claims.
