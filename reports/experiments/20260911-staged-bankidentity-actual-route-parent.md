# Bank-local identity: exact checker behavior, no timing promotion

FW `51373929db63c1908bc9780f5569f8ebb7356597` and HDL
`7bbf1080a98f5ec4e8aefdd81cf6671de8f0dcf1` are preserved on
`codex/starlink-rx-only-do-not-merge-bank-local-identity`, based on guard facts
(`bf817a6bd` / `82be254db`). No radio, PPU, main or primary production HDL
change; production gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implementation and verification

The input checker can compare each raw held 70-bit bank metadata bus with its
admitted descriptor before selecting one comparison bit. The default-off
parameter is enabled only for registered scheduling. No state, latency,
framing, delivery, certificate, diagnostics, reset or public output change.
For X/Z phase, it retains equality of the original bitwise-merged selected
bus: moving a mux through equality is not automatically four-state equivalent.

Complete checker/top inverses prove the limited delta. Each default/enabled
real-checker comparison passes 446534 checks and 8227 clock transitions.
Coverage includes all 70 metadata bits; four-state selector/control/metadata;
initial/middle/final ordinals; healthy 512-word delivery; malformed position
and last; unknown metadata; duplicate start; unmet demand; reset and legal core
waitstates. Three incorrect comparators fail (unknown-selector shortcut,
swapped banks, dropped final metadata bit). This is finite differential testing,
not full formal receiver proof.

**480 tests pass in 74.88 s**, no failures/errors/skips. This includes ten
actual-evidence auditor tests that reject missing cases, incomplete coverage,
disabled equality and short fresh recovery. Existing predicate tests remain
live; historical source inverses use pinned original snapshots where needed.

The actual generated-FFT bench matches all **64512 records** and retains the
same CSV. Service intervals: 3659/3659/4927/11727/3659/3659 clocks. The deliberate
9000-clock reader pause is included in 11727 and excluded from the unchanged
5215-clock diagnostic service bound. Added recovery cases only extend the
overall simulation timeout, not the clock or service requirements.

A default-mode real checker witness agrees across 421667 falling-edge
observations, including 44707 forward and 30240 inverse certified-beat
observations. These include healthy and aborted work, not unique publication
counts. Both owners pass selected/unselected-bank bit corruption at ordinal 32:
selected corruption immediately quarantines and blocks stale work; unselected
corruption preserves a complete healthy result. All four then reset and recover
with 512 correct reads and one actual reader release. Prior fault/reset/stall
tests continue passing. 152 admission/105 completion receipts include aborted
work and do not prove continuous receiver service.

## Physical comparison

| Candidate, default diagnostic recipe | WNS (ns) | TNS (ns) | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 | -451.168 | 704 |
| Guard-fact parent | -1.340 | -463.636 | 821 |
| Bank-local identity | -1.940 | -579.273 | 785 |

**Not promoted.** Compared with its parent, WNS is 0.600 ns worse and TNS
115.637 ns worse, despite 36 fewer failing endpoints. 785/13864 setup endpoints
fail. No post-route directive sweep was applied to this regressing candidate.

Resources: 2805 LUT / 5687 FF / 21 DSP / 15 RAMB18 / zero RAMB36. All 8431
routable nets are fully routed, zero routing errors. Hold +0.062 ns and pulse
+1.830 ns pass; unchanged 100/175 MHz clocks and 114/124 unconstrained I/O.
Source/checkpoint/report audit passes, but physical timing and deployment gates
fail. This remains an isolated subsystem, not full receiver signoff.

Worst path: source-bank held metadata bit 67 -> preflight identity comparison
-> shared guard/fault logic -> output-bank request toggle. Eight logic levels,
7.602 ns data delay, 6.019 ns routing (79.2%). The next path (-1.863 ns) reaches
sticky fast fault from the same source. The local checker refactor did not
remove the broader preflight/publication dependency.

## Next boundary and full deployment gates

Retain the earlier references. Investigate preflight validation and outstanding
publication together, first proving the reachable phase/ownership relationship.
Do not assume preflight cannot overlap pending inverse publication: FFT core
reuse and slow-reader mailbox release are different events. No phase-based
fault exemption or delayed public veto without a complete safety argument.
Any revised registered boundary must preserve diagnostics, reset/fault
cancellation, stale-work rejection and actual reader ACK, and explicitly budget
added cycles before actual FFT and unchanged routing. Further TX removal does
not address this control path.

Keep native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board I/O, sustained capture,
actual 60 MS/s RX calibration and Ethernet/IIO qualification precede `.18`
reversible canary and `.17` PPU Ethernet-only deployment with pinned rollback.
Final gate: 300-second scan, 120 ms valid dwells and blind host GLRT comparison.
No deployment date or continuous native RX claim is established by this result.

## Evidence

[Verified archive](20260911-staged-bankidentity-evidence.tgz) and
[receipt](20260911-staged-bankidentity-evidence.json): 15862409 bytes,
7451 members, all read-back verified. SHA256:
`7526ed1aa0dfb380398a36e0ea5739d9f6552df2ea2f6e6f46fe545917acc47b`.
Actual/synthesis/route finish on first attempts: 167.39 / 99.12 / 49.04 s.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/bank-local-identity-worktree-v1`.
Sibling artifacts: `staged-bankidentity-{prepared,actual,synth,route}-v1`.
Prepared inventory `5871d94dfa6ae322843a8d327624a21aa77ba4461a61a47f0c74ddbda4f3eb4a`;
synthesis DCP `0069854c76e26ad876beb62de5bf82fa4e020f82a08bb8cb16a8ba00046300e0`;
routed DCP `008ccdbdbaad3b89791eca4366655b6da621af571fe39ded26b97deb22b76d4d`.
