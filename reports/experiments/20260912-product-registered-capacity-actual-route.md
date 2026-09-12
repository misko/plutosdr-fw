# Registered product capacity — actual FFT proof, timing still open

2026-09-12. DO NOT MERGE firmware into main.
Branch: `codex/starlink-rx-only-do-not-merge-replay-capacity-buffer`.

## Outcome and decision

The simpler product output stage is functional and meets the unchanged short
service limit: **4,689 clocks versus 5,215 allowed**, with all **64,512 checked
numerical words exact**. **2,229 scoped regression tests and all 82 actual-FFT
fault/reset/stall cases pass.**

Timing is NOT closed: **WNS -1.222 ns, TNS -323.774 ns, 802 failing endpoints**.
Retain this as a tested alternative. Do not replace the lean reference merely
because this is newer: it costs 511 service clocks and the worst slack is
slightly worse than the private-replay parent, despite fewer failing endpoints.

Source FW `e3c218cb3bc6bfac5573540a25bad852a1cb3908`;
HDL `10f773c2918e23daea84bd73bfeea3a197a3b42d`.
Initial source commit `dc999821a` retains the first test-count assertion error;
the source above corrects it and pins the acceptance-aware fault injector.
No radio, PPU or main-branch changes. Primary HDL gitlink is unchanged at
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## What changed

This candidate derives directly from the lean private-replay top, not the
previous head/tail or alternating replay queues. It adds no replay payload
storage and preserves the parent FFT, capture/seal bank and arithmetic.

The existing product identity slot now advertises capacity only while empty.
It does not refill on the clock edge that consumes its old word. Its parallel
kernel capacity summary uses that local occupancy instead of current downstream
product-bank READY. The external product-bank READY signal still has its other
original safety/ownership uses; this is not a claim that every READY path vanished.

The metadata comparison, word/certificate capture, final-word retirement from
the actual bank ownership receipt, both actual publication predicates, faults,
common reset and quarantine remain unchanged. The old first-word write-through
comparison remains implemented and checked even though healthy acceptance no
longer coincides with that first-word retirement.

There are 43 runtime source files, with the preceding private-replay 41 files
unchanged byte-for-byte. Main, synthesis and the corrected auxiliary campaign
use identical runtime profiles and files.

This deliberately changes an internal handshake contract. The old requirement
to demonstrate same-edge product refill is replaced by a requirement that it
never happens, plus nonvacuous first-word capture and retirement. It is not
appropriate to call the new input READY cycle-equivalent to the parent.

## Tests and actual data

The real-mailbox component test preserves the original independent mailbox
comparison, all payload/order/publication checks, 12 successful blocks and
6,144 reads, 420 invalid/X/Z metadata cases, six framing cases, eight
reset/control-fault cases, blocked-final holds, stalls and fresh recovery.
It requires zero simultaneous refills. Mutants restoring refill, bypassing
identity checks, losing abort or dropping an unpublished final are rejected.

There are 40 new focused tests, including exact source transformations,
qualification-parser mutations and acceptance-edge corruption coverage.
The scoped regression comprises the preceding 2,181 tests, eight prior recorder
tests and those 40 new tests: **2,229 pass in 137.93 s** (runner elapsed 138.14 s).
This is not a claim that the sparse worktree's entire historical repository
suite can collect; the earlier missing-evidence collection errors remain recorded.

Healthy actual FFT:

- Six contexts with full-width timestamps, including stalled host readers.
- 9,216 product-slot captures, 18 first-word captures and 18 first retirements.
- Zero same-edge product refills; inverse output streaming retains its original
  independent refill behavior.
- 64,512 exact numerical words against the pinned seven-stream truth.
- Maximum service 4,689 clocks: 511 more than the 4,178-clock parent, 526 below
  the existing ceiling. This is about 26.8 microseconds at 175 MHz, but is only
  a short subsystem service measurement, not sustained 60 MS/s RF proof.

CSV SHA256:
`486fe40fa0cd6d999424683962400244f9e89362299404e297c6d53ee1b27329`.
Cross-stream ordering can change with pipeline scheduling; correctness is
independently checked by stream/job/position and exact data/exponent.

The first auxiliary campaign was REJECTED at fault case 3. Its one-clock
corruption began at a visible replay position without checking READY; the
new bubble meant the kernel did not consume that corruption. Version 2 waits
for an actual acceptance edge, checks the original position/acceptance, forces
the same bad ordinal and verifies it reaches a valid, ready kernel interface.
All original quarantine, no-publication and fresh-recovery assertions remain.
A required terminal witness records the delivered corruption; omission,
duplication or a nonaccepted witness is rejected.

The corrected full campaign passes all 82 inherited boundary cases in 338.19 s:

- 925,076 product-capacity/comparator checks and 75,083 captures.
- Zero refills; 154 first captures and 154 first retirements.
- 1,850,152 private replay comparisons, 11 private-only takes, five private-only
  final words and 2,045 quarantined reference differences.
- 28 delayed guard-fault edges, preserving the registered diagnostic behavior.
- Actual final publication, reset/reuse, invalid metadata, held results,
  both raw resets and fresh recovery remain independently checked.

The archive preserves both rejected test XMLs: a mistaken dictionary-size
expectation (two failures) and an assertion that overlooked the existing reset
cleanup release (one failure). Corrected tests check the exact proof-key set
and unchanged release count. These were harness assertions, not changed RTL
or relaxed publication/deadline gates.

## Routed measurements

Same Vivado 2022.2, xc7z010clg400-1, unchanged isolated 100/175 MHz route recipe.
No added false paths or multicycle exceptions.

| Metric | Lean private replay | Registered product capacity |
| --- | ---: | ---: |
| Worst setup slack, ns | -1.182 | -1.222 |
| Total negative slack, ns | -349.709 | -323.774 |
| Failing endpoints | 930 | 802 |
| Worst 175 MHz setup, ns | -0.970 | -1.222 |
| LUT / FF | 2756 / 5908 | 2735 / 5915 |
| Short service, clocks | 4178 | 4689 |

DSP and RAM are unchanged: 21 DSP, 16 RAMB18 in this subsystem.
There are 8,554 fully routed nets, zero routing errors, +0.043 ns hold slack
and +1.830 ns pulse slack. Setup still fails.

Measured endpoints (ns): product occupancy +1.763, identity +0.728,
kernel history +0.378, kernel index +3.173, forward-position CE -0.160,
kernel next-start CE -0.382, descriptor CE +0.980/data +2.013,
output occupancy +1.014, product publication -0.757, output publication -1.088.

The kernel next-start path is reduced to five logic levels but still crosses
reset release, stage fault/capacity and a wide sequence enable. Its data delay
is 5.807 ns, 81.470% routing. The intermediate reset/run-derived net has 2,304
loads. Compared with the immediate private-replay parent, its -0.382 ns slack
is not an improvement over -0.364 ns.

The overall worst path is engine metadata bit 12 through preflight equality
and preparation-fault distribution to a guard fault-reason register: eight
logic levels, 6.929 ns data delay, 79.102% routing. That is now the next
concrete control-path target; arithmetic removal or TX removal does not address it.

This route still has 114 unconstrained input and 124 output ports. It does not
establish full receiver CDC/reset/physical signoff. Early-route receipts remain
explicitly exploratory; the later complete campaign is separately matched to
the routed runtime and checkpoint.

## Next experiment and deployment path

Inspect every consumer of the current preparation-fault result, separating
where an immediate publication/admission veto is essential from where a
registered diagnostic update is sufficient. Evaluate a bounded staging or
localization of held-metadata validation and diagnostic distribution; prove
snapshot identity, fault latency, reset/expiry and final publication before
routing. Do not simply delay the shared fault wire, ignore current metadata
errors, or waive the failing path.

Use the faster lean private-replay design as the comparison reference; retain
this slower candidate as an alternative. It has not demonstrated a sufficient
overall advantage to become the mandatory integration baseline.

All original release requirements remain: native 60 MS/s fine search,
independent 2.5 MS/s CI16 inspection over IIO, 15/30/60 MS/s qualification,
independent host GLRT on matching observations, eight high/low targets,
120 ms valid dwells and a 300 s scan. Short FFT simulation is not a substitute
for sustained full-receiver scheduling, RX calibration or DMA/Ethernet tests.

Still required before deployment: whole receiver routing/timing and CDC/reset
at actual board clocks, continuous acquisition/fine search and inspection,
60 MS/s analog calibration, paired live proof, clean stop/restart and rollback.
Do not change the shared board 200 MHz IDELAY reference to match this isolated
175 MHz test.

Deploy only to serial-attested .18 canary
`1040007c4a94000211000b009186843ef2`, then outdoor Ethernet-only .17
`104000bac4950008230026001b440a003a` through pinned reversible PPU.
.17 remains RX1-only on the powered LNB. No TX. .14/.20/.21 excluded.

## Pinned evidence

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/replay-capacity-buffer-worktree-v1`.
RAM evidence:
`/dev/shm/starlink-product-capacity.9xKDnOQI`.

Main/synthesis snapshot:
`0094714206f91f0eea4a3006bbc3369897640bacb8796a941fca1f15c2d4325d`.
Corrected auxiliary snapshot:
`14afe634c4f6b4d118a039125f552770dca2c1df0676883a4e52bbe0af753fd1`.
Synthesis DCP:
`9060caf744458f3b603bc424bf728a9bc017841226e9e060ee931b8b9961154c`.
Routed DCP:
`d9fbe1f6a2c7fa5e42b2ab9d42c88551fcdd9f611363f7aa46b3908361f8c5e6`.

Curated archive `20260912-product-registered-capacity-evidence.tgz`:
9,809,699 bytes, 596 members. SHA256:
`d7f2cf9c9f86493d6ec494acb3d6eb4e7d1c44861bd72b1df4fdc95042fb7827`.
Includes prepared sources, actual logs/CSV, failed/corrected auxiliary evidence,
component artifacts/XML, scoped regression receipts, synthesis and routed
checkpoints, timing/endpoint reports, and the re-audit/archive helpers.
Sequential payload SHA256, inventory, gzip CRC and unchanged source checks pass.
Tracked under `reports/evidence/`; intentionally sparse in worktrees to avoid
duplicating large files on the nearly full workspace volume.
