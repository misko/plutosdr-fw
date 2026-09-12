# Ownership-derived descriptor lock — DO NOT MERGE

The experiment is functionally equivalent over the tested scope, but physical
timing regresses. **Do not promote it or deploy it.** The previous retry-admission
candidate remains a comparison baseline, not a timing-qualified release.

Branch (FW and HDL): `codex/starlink-rx-only-do-not-merge-ownership-lock`.
Parent FW `2a4f232f8a8cdff790936543f2286c808e89550c`;
parent HDL `05756d03d9781f0d3af5b3186ae5d3e2cd8ab6b9`.
All 43 parent runtime files are unchanged; the experiment adds one selectable top.

## Exact implementation and lifetime contract

The only runtime changes, enforced by an exact source transform, are the module
name and replacement of the separate completion-driven descriptor-lock register:

```verilog
wire output_descriptor_locked =
    output_publication_busy || retained_published;
```

Its old reset/set/release assignments disappear. Completion acceptance,
descriptor capture and validation, publication, current-fault vetoes, reader
ownership, guards, scheduling, FFT, buffers and clocks are otherwise unchanged.
No arithmetic or payload RAM is added or removed.

Mailbox busy starts on the original checked completion acceptance edge and
persists through final replay, actual publication, real reader ACK and ledger
release. When its phase returns to EMPTY, the existing retained-published flag
bridges the extra edge until the top consumes the release receipt. Busy alone
would unlock one cycle early. A fault on that bridge suppresses release, leaving
the published flag and original lock held until coordinated reset.

An independent old completion-driven lock runs beside the actual candidate,
compared before and after every fast clock edge, including quarantine.
This tests the lock representation; the inherited FFT/publication/fault
observers continue checking their original contracts.

## Verified functional results

- **2,330 scoped tests pass**, final run 164.350 s, 131 inherited modules plus
  one ownership-lock module (31 new cases); not the whole repository.
- New real-mailbox tests cover release/reallocation, backpressure, pending/
  COMMIT/replay/post-publication abort, reset and fresh recovery.
- Six extra cases inject known/X/Z abort or bank fault exactly on the
  EMPTY-to-release bridge. Each holds the descriptor and blocks release/reuse,
  then verifies a fresh 512-word recovery.
- Four unsafe expressions are deliberately rejected: busy alone, published
  alone, unlocking on fault, and never unlocking.
- Healthy actual FFT: **64,512 numerical words exact**, **4,178 clocks**,
  177,096 lock comparisons, 18 completions and 18 releases, 36 bridge observations.
  No added latency; the original 5,215-clock short-service ceiling is unchanged.
- Full inherited actual-FFT campaign: **all 92 cases pass**, 366.835 s.
  1,841,886 lock comparisons, 129 completions, 110 releases, 220 bridge
  observations and 2,805 quarantined lock holds. The 316 admitted jobs still
  match the original admission certificate. All 28 delayed guard-fault
  observations remain covered.
- Main, synthesis and auxiliary profiles use the same 44 runtime files.

Numerical CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

The first scoped run had 2,324 passing cases but was correctly rejected by its
source-stability gate: six tests were added while it was running. Its receipt
and XML are retained as a rejected observation. The final expanded run above
has unchanged sources. No rejected receipt is counted as qualified evidence.

## Physical result — rejected

Same actual FFT and frozen 100/175 MHz OOC route, no timing exceptions added:

| Metric | Retrying admission parent | Ownership lock |
| --- | ---: | ---: |
| Worst setup | -1.269 ns | -1.267 ns |
| Same-175 MHz worst | -1.001 ns | -1.229 ns |
| Total negative slack | -295.708 ns | -713.969 ns |
| Failing endpoints | 811 | 1,299 |
| LUT / FF | 2,739 / 5,920 | 2,741 / 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Short service | 4,178 clocks | 4,178 clocks |

8,554 nets fully routed, zero routing errors. Hold +0.027 ns, pulse +1.830 ns.
114 inputs and 124 outputs remain unqualified. No physical/receiver signoff.

The new same-clock worst path is global latched fault through output-stage and
output-ledger fault/capacity logic into registered scheduling held phase:
eight logic levels, 6.812 ns data delay, approximately 79% routing.
The following path ends at the mailbox completion-pending register
(-1.193 ns, nine levels). Removing one destination register did not remove
the cross-block dependency or its fanout.

Overall worst remains an unqualified held-metadata 175-to-100 MHz crossing.
It is not waived; same-domain timing also fails independently.

The same updated endpoint probe was run against both pinned checkpoints:

| Endpoint | Parent | Ownership lock |
| --- | ---: | ---: |
| Guard reasons | -0.669 ns | -0.969 ns |
| Admission snapshot valid | +0.009 ns | -0.524 ns |
| Admission snapshot good D | -0.697 ns | -0.713 ns |
| Admission consumed | -0.040 ns | -0.576 ns |
| Guard active | -0.908 ns | -0.876 ns |
| Global fault register | +0.320 ns | +1.521 ns |

The first probe rejected the candidate because physical optimization added
a seventeenth diagnostic-register pin, a replica of owner 0 reason bit 3.
Pinned netlist enumeration identified it. The corrected probe requires all
16 original diagnostic pins and permits that one extra replica; it does not
treat missing pins as passing. Both corrected observations pass. The rejected
probe and enumeration log are retained.

Additional candidate endpoint slack: forward-position CE -0.805 ns,
kernel-next CE -0.208 ns, product publication -1.039 ns,
output publication -0.767 ns. This is not an aggregate improvement.

## What the result changes next

Do not stack this representation onto the next implementation. Start from an
explicit pinned baseline (retry admission and lean parent remain comparisons).
The measured problem is the combinational fault/readiness round trip, not the
lock register alone or transmit logic.

The next bounded architecture experiment should separate:
1. Local private ownership/completion receipts, with short registered updates.
2. Current checked authorization of publication, reuse and new jobs.
3. Stable fault/cause evidence and coordinated cancellation/reset.

First enumerate externally consumed diagnostics and the exact earliest fault
veto edge. Then break a specific ledger-to-guard-to-scheduler readiness
dependency using registered private capacity/retirement state; avoid routing
already-known global quarantine back through every local error summary.
Do not delay first-fault publication prevention or erase required diagnostics.
Compare actual old/new published results and cancellation/recovery behavior.
A local state change during quarantine must never become publication, reuse
or fresh admission. Route the actual FFT/buffers early, compare all endpoint
groups and preserve the service limit; do not optimize only one destination.

The full goal is still open: native 60 MS/s fine search, independent 2.5 MS/s
CI16 IIO inspection, causal acquisition/CFO/fine processing, eight high/low
targets with 120 ms valid dwells over 300 s, independent host GLRT, continuous
RX/DMA/Ethernet and actual board-clock/CDC/reset qualification.

After isolated closure: full receiver route, real 60 MS/s calibration,
sustained native plus inspection capture, serial-verified .18 canary,
then pinned reversible Ethernet PPU deployment to .17 and real reception/
replay comparison plus clean stop/restart. A passing short FFT bench is not
continuous receiver or deployment proof.

## Evidence and radio scope

Artifacts: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/ownership-lock-artifacts.9ub0wG1x`.

Main/synthesis prepared pin:
`fd893cab510d8a11bf41366d2e8d11458faf90106b04881952337e693930d122`.
Auxiliary pin:
`3b3615d49f950d95d040c85b4f968ae01cd057f53a99da9f7f2eb91e3a340471`.
Synthesis DCP:
`aed40a8fc1ea537c21422677190832656b2ed81d412bf00290b7e85463c452d3`.
Routed DCP:
`11fe9fea0d2d3d0e8f0a4daacd3a02dbf581b47710c19c1eb95fd3f8a6594189`.

Archive creation rechecks frozen sources, matching runtime files, numerical
and lock witnesses, final regression sources/XML, route/probe inputs and DCPs.
Verified archive: `reports/evidence/20260912-ownership-lock-evidence.tgz`,
8,837,230 bytes / 549 regular members. SHA256:
`a4990bbbf93b396d9423e08645bfe4127460e33001f47ecd9f711823a840f159`.
The adjacent archive receipt records per-member SHA256, inventory, gzip CRC
and unchanged-source verification.
No radio, PPU or main branch was touched. PRIMARY HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

- .18 canary: `1040007c4a94000211000b009186843ef2`.
- .17 outdoor Ethernet-only receiver: `104000bac4950008230026001b440a003a`,
  powered LNB on RX1 only.
- .14/.20/.21 remain excluded.
