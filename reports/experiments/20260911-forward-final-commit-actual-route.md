# Forward final commit: local path improvement, no overall promotion

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-forward-final-commit`.
FW `9c21b369aaf70d842411ec065d78ee3ca0a1ac25`;
HDL `dbff0b303322d2d44d96a60ae2185cee981d6f2e`.

The forward guard now uses its existing forward-retirement fault contract for
the SAME-edge final handshake. In a known forward phase, the inverse output
mailbox's current framing check cannot apply; sticky mailbox faults and every
other current veto remain. Disabled callers, inverse phase and unknown phase
retain the original expression. Public valid/commit, diagnostics, state storage,
status/exponent qualification, reset and readiness remain unchanged.

Only the guard changes at runtime. An additive actual-FFT witness compares its
internal final decision to the original public commit AND readiness expression
for both owners. Source inverse tests reconstruct the parent runtime/bench.

## Verification

1002 regression tests plus seven evidence-gate tests pass: **1009 distinct**.
The actual guard passes 262144 four-state handshake comparisons across four
enabled/disabled forward/completed-input configurations. Removing fault, reset,
qualification or fallback protection, or violating the phase contract, fails.

Both actual generated-FFT campaigns pass: 503564 main and 437625 auxiliary
handshake observations, including 98/84 forward accepts. All 64512 numerical
records/CSV bytes and service clocks `3663/3663/4929/11729/3663/3663` match
the parent. The original late-fault, reset, publication and recovery cases pass.
Matched routing requires complete nonvacuous witnesses from both runs.

| Metric | READY-absorption parent | Forward final |
| --- | ---: | ---: |
| Global WNS (ns) | -1.245 | -1.331 |
| Same-domain WNS (ns) | -1.046 | -1.189 |
| TNS (ns) | -245.991 | -277.204 |
| Setup failures | 453 | 526 |
| LUT / FF | 2728 / 5790 | 2732 / 5798 |
| Handoff → ACK (ns) | -1.046 | -0.255 |
| Product position → active (ns) | -1.045 | +0.152 |

Queries cover all five handoff-exponent and nine product-position registers.
The exact handoff-to-active endpoint no longer has a reported path from those
five exponent sources; handoff-to-fast-fault improves -0.966 to -0.555 ns.
This is not a claim that every handoff dependency vanished.

New same-domain worst: actual FFT flushing register → input READY → input/fault
accounting → fast_fault, seven logic levels, 6.851 ns delay, 78.7% routing.
Global worst is output metadata bit 4 crossing 175 to 100 MHz. All 8480 nets
route without errors, hold +0.057 ns and pulse +1.830 ns pass; DSP/RAMB18 stay
21/15. Reset structure passes. CDC remains nine CDC-3 / 208 CDC-15, unqualified.
OOC 114/124 input/output ports remain unqualified; no constraints were changed.
A noncritical forward-wire declaration-order warning is retained in the raw
logs. Correct declaration order in a follow-on revision, with fresh matched
evidence; the measured snapshot is unchanged.

## Decision and next gate

Do not promote this overall regression. Preserve it and the better overall
READY-absorption parent. Next prove parallel capture of independent fault groups
at the existing sticky-fault register boundary. Require equality to the scalar
latch under reset, X/Z, simultaneous faults, sticky persistence and forced
summary inputs. Keep immediate current-fault publication vetoes; do not introduce
an extra fault-response cycle. Only integrate and route after that contract is
established. The current candidate alone does not fix timing closure.

Native 60 MS/s fine search and 2.5 MS/s CI16 IIO inspection remain required.
Full receiver timing/CDC/board clocks, real 60 MS/s RX calibration, continuous
RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans remain
deployment gates. Then qualify pinned PPU/rollback on .18 before Ethernet-only
.17. No radios, PPU/main, primary HDL gitlink or TX were changed; .20/.21 excluded.

## Evidence

[Archive](20260911-forward-final-commit-evidence.tgz),
[read-back receipt](20260911-forward-final-commit-evidence.json):
33,579,112 bytes / 6366 members, SHA256
`1a25805c7bdd1be43ffdc7df4b7be61c8839567d744322347bee57216e3cbf52`.
Includes frozen sources, actual FFT logs/CSV, synthesis/routed checkpoints,
tests, both parent/candidate targeted paths and CDC reports.
Raw: `/dev/shm/starlink-forward-final.VUVSznt1`.
Prepared SHA: `cb90644fc6c252e7a941bc57ef3c32c87f3b7b59d51d3b94c547114bee68c16a`.
Routed DCP SHA: `92b66696bdb3e9b3cc7ba12d61e825627910bf53c20516ebed8973c328aed52f`.
Parent: [READY absorption](20260911-ready-logic-absorption-actual-route.md).
