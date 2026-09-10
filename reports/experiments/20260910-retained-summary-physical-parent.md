# Offered-input summary: actual PASS, routed timing still FAIL

The source-qualified summary refactor completes synthesis and routing with the
same clocks and no timing exceptions. Worst setup slack improves from -2.697 ns
to **-2.504 ns**, but this is still a failing diagnostic build, not deployable
firmware. The full receiver, continuous ingress/native-fine/IIO schedule, real
board clocks and radio calibration remain unqualified.

## Verified physical preparation and synthesis

Root72340 terminal0: **77 tests PASS in1.20s**,24 source files unchanged. The
combined gate retains60 policy tests and adds17 exact unbound inverses and
read-only checks of the original accepted actual run. It verifies original,
executed and live116-source inputs, full results and the original owner receipts.
The independent initial unbound60 gate also passed previously.

Real preparation produces133 inventory entries with SHA256
`1760f6d51c2438bd22ff12dfeccb18aa83a528b54ac0b71992efa27c32160a2b`.
The runner selects the exact16 runtime files, including the four summary files,
and enables the summary option. Source-specific owner changes are four literal
mapping groups from the previous reviewed synthesis owner. No clock, numerical,
reset, service or source-identity check was weakened.

Root98534 terminal0,185.7805s: synthesis produces DCP
`2348ac8205738a178e11d3f51c8d5b46199ab8548a57573bae0edd785f3f5eb5`.
Independent source/hierarchy/resource/constraint audit passes. Original and
copied116-source checks pass, all133 prepared inputs and24 preparation sources
are unchanged. No black boxes. One shared FFT and all three payload banks remain.

Mapped synthesis resources:2248 LUT,4759 FF,21 DSP48E1,15 RAMB18. Relative to the
preceding actual-qualified retained candidate: **+6 LUT, no FF/DSP/RAM increase**.
These are isolated-block resources, not complete-radio utilization.

## Routed result

Root26806 terminal0,64.7586s. The unchanged route runner produces DCP
`83d268fff699dae1ca3fca8bd1debddd04562590a284f982e05844bdb1059d38`.
All7253 nets are fully routed, with0 routing errors. Tool success is separate
from timing acceptance:

| Metric | Previous retained candidate | Offered-summary candidate |
|---|---:|---:|
| Worst setup slack | -2.697 ns | **-2.504 ns** |
| Total negative setup slack | -981.622 ns | -829.822 ns |
| Failing setup endpoints | 848 | 679 |
| Worst hold slack | +0.037 ns | +0.049 ns |
| Failing hold endpoints | 0 | 0 |
| LUT / FF after routing | 2333 / 4764 | 2344 / 4766 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

Pulse-width slack is+1.830ns,0 failures. There are11060 setup endpoints and66
control sets. Clock-pair setup/hold slacks are100→100:+2.512/+0.100ns,
100→175:-0.546/+0.162ns,175→100:-1.236/+0.074ns,
175→175:-2.504/+0.049ns. Five critical CDC findings,139 warnings and3 informational
findings remain. The diagnostic still has114 unconstrained input delays and124
unconstrained output delays. Rounded independent100/175MHz primary clocks are
not a qualified board-derived clock relationship. No exceptions were added.

The first independent route collector rejected two identical `Slice Registers`
rows in the utilization report. Both are legitimate totals in separate sections.
Its source and failure are preserved. The corrected collector requires exactly
two equal register totals and exactly one occurrence for each other selected
resource; no vendor artifact or timing criterion changed.

## What remains critical

The worst path now starts at `epoch_barrier/fast_release_reg` and ends at
`cutover/owner_inverse_reg/D`:8.163ns data delay,1.758ns logic and6.405ns routing,
10 LUT levels. It traverses reset-qualified mailbox readiness, retained output
reservation, destination preflight, common fault and admission logic. The first
large reset-qualified net has1226 reported loads. This is a same-domain path
to a synchronous data pin; calling it a reset path does not justify a waiver.

The top20 setup paths start only from epoch release or held-phase state. Other
destinations include guard/retained-owner state and scheduler receipts. The
earlier direct metadata/write-side endpoints are not in this top20; they have
not been proven absent or closed elsewhere.

Next is a source-bound review of the common destination/preflight/admission
logic: independent bank-local checks before scalar phase selection, redundant
reservation/reset factors with explicit premises, or a registered private
preflight/admission boundary. Any candidate must preserve immediate fault
evidence and prevent invalid starts, publication and ACK/release, including reset
and X/Z cases. The previously rejected pulse-only forward-commit change remains
rejected. No next RTL candidate is accepted by this report.

## Evidence and publication

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `retained-summary-synth-parent.39BysdkS`: independent77, full source snapshots,
  real preparation, original synthesis owner/process/logs/DCP and independent audit.
- `retained-summary-synthesis-prepared-v1`: immutable133-entry physical input package.
- `retained-summary-route-parent.qxOkezJN`: original route owner/process, complete
  reports/DCP, first collector failure and corrected independent audit.
- `retained-summary-publication-parent.pcs0TXoZ`: independent Git-object audits
  of2401 preparation and493 actual archive payloads. Actual evidence is published
  at FW`c4ae7252189b11f7b2e04e6b2ea2a381ec72b378`, HDL
  `b013cb91ffc8038e39726109ebfe5ee5afe032ed`, both remote DNM heads verified.

All original vendor handles are terminal. No radio/PPU action, main merge,
production gitlink promotion or timing waiver occurred.
