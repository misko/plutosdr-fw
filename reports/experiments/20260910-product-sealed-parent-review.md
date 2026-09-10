# Staged product validation: independent offline review

**848 tests pass independently; top integration and physical timing remain unproven.**
Parent original process87683 exited0, 848 passed in17.81s. Parent read both new
RTL modules, both testbenches, both Python test files and the implementation
report completely before execution. A separate read-only audit verifies all
seven frozen source hashes, the actual compiled fixture closure, 848 XML
cases with zero failures/errors/skips, healthy receipts and the graph netlist.

Reviewed checkpoint: FW `a599e71889da325c0838447bcdf2f41d5ca04cab`,
HDL `d7b73a9b8012ac7ace5e3c697bd4acdfcdad4cea`, on the separate
`codex/starlink-rx-only-do-not-merge-rom-prefetch` branch. Runtime/test source
checkpoints are HDL `1cbbab6b55f94f22791f97ff66605acc8b074dda` and FW
`99defe9eb6c310de504aa8cbfbca9d6d699d1a7f`. Packaging changed no tested bytes.
Publication of this reviewed checkpoint to that alternate branch is authorized;
this report alone does not assert remote verification.

## What this proves

The additive, default-inert adapter binds product identity to real forward
completion, then stages all75 metadata bits through the unchanged sealed bank.
Its three-slot reader checks every offered word, including stalled offers,
and assigns GOOD only to a matching taken slot/position/lease. A current bad
verdict vetoes handoff; copied canonical metadata is only exposed for a token
whose original metadata was checked. No production caller is changed.

All848 tests pass, including bit-wise producer/read corruption, framing,
stalled offers, stale verdicts, current faults, default/X/Z options, one-sided
epoch resets and executed missing-check/release mutants. A real prototype
handoff bug found during development is preserved with its failing witnesses;
the corrected current-verdict fence is independently exercised here.

Eight healthy leases each deliver512 consecutive exact nonzero products to
the real input guard, with511 clocks first-to-last and no holes. The fixture
uses real guards and spectrum arithmetic, but synthetic FFT result actors:
it does not establish FFT numerical accuracy or complete pair service.

Measured fixture latencies: final product to seal2 clocks, publication3;
forward completion to publication6; publication to checked-head handoff10;
handoff to first core transfer2; actual last core transfer to lease release1.
The1555-clock admission-to-release interval excludes actual FFT execution.
The earlier provisional+12 allocation is not a measured receiver overhead.

The continuous-control graph has3123 nodes and no cycles; a deliberately added
release feedback loop is rejected. Raw offered product metadata is absent
from the publication/handoff/core-valid/release combinational cones. This is
an Icarus connectivity audit with procedural state/input cut points, not
mapped LUT depth or physical timing. Logical declared state is760 bits
(bank317, reader350, issuer93), plus one512x36 RAM; external purge/CDC and
existing guards/product are excluded. Mapped resource cost is still unknown.

## Integration findings and next gate

The independent branch's read-only top audit identifies four required seams:

1. Pre-admission reusable capacity must remain distinct from product READY,
   which is false until the producer owns a lease.
2. Inverse preflight needs a checked head/descriptor before RUN; core VALID
   deliberately remains false until the consumer is enabled.
3. The scheduler needs a retained, health-qualified handoff receipt after the
   real forward guard releases busy; a one-clock handoff pulse is insufficient.
4. Feeding the complete downstream delivery-fault cone back into core VALID
   creates a loop. Keep complete current faults on global/result publication;
   use independent raw causes, duplicate-start and same-token verdicts at the
   queue, with explicit source/control graph verification.

Before top edits, finish the source-specific design against P1 alone: bind
the inverse admission descriptor/lease to the checked head, preserve all75
offered checks, distinguish source/forward identity checks, explicitly retain
late raw-event detection, and implement fresh common-epoch purge rather than
assuming the fixture's external attestation. Extend primitive interfaces and
negative witnesses first if required. No untested combination with the
inverse-sealed or retained-output alternatives is authorized by this review.

Then require default-old comparison, actual-controller phase/READY/fault tests,
actual FFT execution and measured pair deadlines before a physical trial.
The last P1 route still fails WNS-1.492ns; these offline results do not close it.

## Parallel recorded-history and reset-contract work

Parent fully reviewed the inverse saved-WDB loader, Tcl and64-snapshot plan,
then authorized one read-only query. Original35055 exited0 in7.798s with9472
values across115 arithmetic,14 guard and19 ownership paths. Parent fully read
the interpretation script and independently repeated it with only three literal
path changes; the whole-source inverse was checked. The output is byte-identical:
SHA `e7eea11977c44c60a2b663010e2eb1174363d4446222ef8560d609ad07311d6a`.
All64 full155-bit guard snapshots agree,116 originally reset/flush-qualified
full119-bit arithmetic comparisons agree, and18 post-edge ownership events
cover two sampled lifetimes. Pre-edge transfer signals and exact event times
are also checked. The final pre/post counter difference matches the original
finish boundary; no comparison is removed to hide it.

All215 owner inputs and original filenames remain unchanged. A vendor settings
sidecar appeared only beneath the separate WDB-copy directory. The original
simulation was not advanced. This bounded physical-time history inspection is
not a proof of all same-timestamp event-region ordering or physical hardware.
Parent archive `20260910-inverse-wdb-parent.tgz`:4338 bytes, SHA
`81d3da98599aff670a77e806798ef9fdd93896238bd25fab9e6665aa601c4c2a`;
tar comparison exited0. The owner is archiving the full query separately.

For retained-output scheduling, parent independently checked PG109 pp11-12:
reset reinitializes pending load/transform/unload work and requires at least
two asserted clocks. This supports an explicit core-job reset boundary, not
an invented guarantee of a particular quiet-after-release latency. Keep the
additional quiet observation and real configuration READY handshake, with no
gap in raw-event monitoring. [AMD FFT v9.1 product guide](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/xfft/v9_1/pg109-xfft.pdf).

## Parent evidence and scope

Recovery: `product-sealed-parent.qo5EiWU4` under the persistent20260910 build
recovery root. XML SHA
`92e97b822e12f194b7e4410f83b90f8d2d34527e17d2324d3b44e2d0e222e955`.
Archive `20260910-product-sealed-parent.tgz`:1,224,246 bytes, SHA
`9f9d1428c10c00b8cda9b633de77c65be26d5150e95bb38328520b012daed4db`.
Includes all parent case artifacts, compiled fixtures, XML, verifier and its
receipt; pytest convenience links ending `current` are excluded. Tar comparison
against retained originals exited0.

No radio, PPU, production HDL gitlink, firmware-main, clock constraint or
acceptance-threshold change. Full receiver timing/CDC/IO, actual60 RX
calibration, causal native fine search with canonical15 coarse acquisition,
independent2.5 MS/s IIO, eight-target120ms/300s scanning, `.18` canary and
`.17` Ethernet/RF verification remain required for completion.
