# First compact ownership component — tested, not integrated or timing-qualified

Implemented a separate two-entry descriptor table as the first component of
the proposed control simplification. Complete 70-bit descriptors are stored
once; commit/release/lookup use 32-bit generation tags. The table rejects stale,
duplicate and wrong-state commands, quarantines aborts, preserves private fault
evidence, and never wraps tag identity within a coordinated epoch.

36 tests pass, including three 3000-command random scoreboards, every descriptor
bit, every tag bit, two simultaneous owners, backpressure, reset/abort, tag
exhaustion, sixteen X/Z cases and five intentionally broken RTL variants.
Initial tests failed only on the simulator's optional finish footer; the bench
uses `$finish(0)` now. All earlier test outputs remain in the evidence package.

The final combined regression passes **190 tests in 45.65 seconds**: destination
actual preparation/runtime/algebra, physical-preparation policy, and the current
descriptor-table suite. Its [JUnit report](20260911-destination-combined-regression.xml)
is published separately from the earlier evidence archive. This is regression
coverage, not an additional routed timing or full receiver test.

An early physical probe registers all inputs and outputs around the table.
It is **not** the complete FFT island or receiver, and its numbers cannot be
compared with whole-island slack as an achieved improvement.

| Experiment | Setup WNS | Setup failures | Table LUT/FF | Hold slack |
|---|---:|---:|---:|---:|
| Whole-tag comparison | -0.012 ns | 4 | 180 / 242 | +0.152 ns |
| Parallel comparison | -0.246 ns | 67 | 194 / 242 | +0.144 ns |

Both fail setup timing. No threshold or clock was relaxed. The second rewrite
was reverted; its exact source and routed checkpoint remain archived. The
unchanged clock period is 5.714 ns. Both probes use no DSP/RAM and include 282
additional boundary registers. Their 172 input/111 output delays and physical
clock-source location are not qualified. Vendor handles 11480 and 92287 are
terminal; independent audits cross-check source snapshots, reports and DCPs.

The critical first-probe path is commit-tag validation → shared fault decision
→ next-tag register enable. The next change is a typed ready/valid command
interface with validation registered separately from applying ownership changes.
Initially permit only one outstanding control command; this keeps slot ownership
stable between validation and application while sample capture and FFT arithmetic
continue independently. Abort/reset must cancel pending responses, and no failed
or stale command may authorize publication or release. This new latency contract
must be explicitly tested rather than claiming old cycle-identical behavior.

The table manages **descriptors, not payload RAM**. It does not yet replace any
live controller, validate FFT output, or implement IIO. A commit still requires
real validated payload-buffer authority. Coordinated reset/drain of all token
holders is required before resetting its generation counter. These are integration
requirements, not properties established by the isolated testbench.

## Preserved evidence

[Curated evidence archive](20260911-destination-and-slots-evidence.tgz):
12,857,182 bytes; 1859 regular members, all verified against the embedded manifest.
SHA256 `9d74caf540adc60d70341cb027209712daa25f500a73b577937072a96f9dad4b`.
Includes the destination actual numerical result/source snapshots, both complete
destination physical reports/checkpoints, both table variants and their tests.
Vendor caches and most inherited mock fixtures are explicitly excluded; full
local originals remain under the recovery root. This is not a firmware package.

Remaining release path: staged controller → actual FFT/buffer integration and
service-deadline tests → routed full receiver/CDC/reset/board qualification →
sustained 60 MS/s and independent 2.5 MS/s IIO → `.18` canary → `.17` PPU Ethernet
deployment and the 300-second scan with 120 ms valid dwells and blind host GLRT
comparison. No radios, PPU code or main branches were changed.
