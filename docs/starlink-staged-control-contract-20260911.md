# Staged ownership/control simplification — experimental, DO NOT MERGE

The complete destination FFT island is numerically correct but fails routed
timing at -3.106 ns. The worst paths traverse metadata validation, fault
aggregation and ownership enables. The next architectural work separates
validation from applying ownership changes; no receiver/radio uses this code yet.

## Implemented first component

`hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_descriptor_slots.v`
is a two-entry descriptor-ownership table. It stores each complete 70-bit
descriptor once, and uses a 32-bit internal identity for commit/release/lookup.
It does not contain FFT arithmetic, payload RAM, an FFT scheduler or IIO logic.

Rules currently implemented:

- Allocation captures an immutable descriptor into a free entry.
- Only a matching owned entry can commit; only a matching committed entry can
  release. Commit/release are pulses, not level-held retry requests.
- Independent entries can transition together; a just-released entry cannot
  be reallocated until the next edge.
- Stale, duplicate, wrong-state or unknown transition commands quarantine the
  epoch. Abort is a direct fail-closed scalar. Quarantine removes all lookup
  and committed-result authority while preserving private evidence.
- Generation numbers never wrap within an epoch. Exhaustion blocks new
  allocation but lets valid existing owners finish. The 32-bit default is not
  shortened to obtain a passing timing result.
- Reset is a coordinated epoch boundary. All external holders of old tags
  must be reset/drained too. The table does **not** prevent aliasing if a caller
  resets this table alone and later injects a pre-reset tag into a new epoch.

The two entries are metadata capacity, not permission to overwrite payload RAM.
The actual controller must respect the real source/product/output buffer owners.
In particular, a single output RAM cannot hold two independent results merely
because this table has two committed descriptors. Commit must come from a
validated completion with real payload-buffer authority, never raw FFT TLAST.

## Tests and early physical measurement

The transaction model exercises two-job overlap, blocked allocation, independent
release, every descriptor bit, every tag bit, reset/abort, stale/duplicate events,
and tag exhaustion with 1/2/4-bit test configurations. Three fixed random seeds
exercise 3000 commands each. Sixteen X/Z cases cover control validity and tag
lookups. Five executable RTL mutants must fail: early release, ignored identity,
tag wrap, descriptor truncation and ignored abort. Current total: 36 tests.

First 13-test attempt failed only because the simulator emitted its optional
`$finish` footer. All RTL comparisons had passed. The bench now uses `$finish(0)`;
the original logs and failing JUnit remain. The later 34- and 36-test suites pass.

The physical probe registers all transaction inputs and result outputs around
the table. Same xc7z010clg400-1 and 5.714 ns clock; no timing exceptions.

| Table implementation | Setup WNS | Setup failures | Table LUT/FF |
|---|---:|---:|---:|
| Whole-tag equality | -0.012 ns | 4 | 180 / 242 |
| Parallel comparison experiment | -0.246 ns | 67 | 194 / 242 |

Both **FAIL**, despite clean routing and passing hold. The comparison experiment
is reverted; exact source snapshots and routed DCPs of both remain available.
Each probe has an additional 282 boundary registers, no DSP or RAM blocks.
These measurements are not improvements of the complete island: they are much
smaller, differently scoped designs. Their 172 input/111 output delays and
physical clock-source location are unqualified. No board timing claim follows.

## Next implementation: a genuinely staged command interface

The first table still lets a tag comparison feed a same-cycle shared fault
decision and allocation enables. The next version should remove that dependency:

1. Accept one typed command through ready/valid: allocate, validated commit or
   actual-reader release. Capture the command and validation result in registers.
2. Apply the validated command on the following edge using only the registered
   opcode, slot and validation result. Return a registered response/token.
3. While that command is pending, block conflicting ownership changes. Starting
   with one outstanding control command is intentionally simple: it prevents
   the validated slot from being freed/reallocated before the command applies.
   FFT arithmetic and sample capture continue independently during these cycles.
4. Keep abort immediate and scalar. Reset/abort must cancel pending commands and
   responses. Invalid commands must never produce a success response or result
   authority. Exhaustion still requires coordinated quiescence, not wraparound.
5. Treat this as a new private scheduling contract. Command-error reporting has
   defined pipeline latency; do not claim cycle-identical behavior to the old
   controller. Payload safety and publication fences remain mandatory.

Tests before integration: transaction scoreboard including command backpressure,
pending abort/reset, concurrent attempted updates, stale responses, wrong-state
commands, tag exhaustion and exact response ordering/latency. Route this module
early with registered boundaries and measure the complete command-to-response
path, not just a comparator. Then connect the actual FFT and payload buffers,
verify full numerical/frame results and the coarse-block service deadline.

The final receiver must still provide native 60 MS/s fine search and independent
2.5 MS/s IIO recording, causal CFO/candidate handling, full board timing/CDC/reset,
real RX calibration, `.18` canary and `.17` PPU Ethernet deployment, followed by
the 300-second/120 ms-dwell blind FPGA versus host comparison. None is replaced
by this component-level prototype.

## Evidence

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `staged-slots-parent.quULATYQ`: initial footer failure and passing test revisions.
- `staged-slots-route-parent.0wh1bZVH`: source-frozen 34-test gate, first route/audit.
- `staged-slots-route-v2-parent.BCFXBat7`: 36-test gate, rejected comparison route/audit.

The exact comparison candidate is preserved in the v2 `source_snapshot` and
`run` directories, although it is not retained as the active module source.
