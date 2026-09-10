# Retained-output prototype: independent full offline gate

Parent original46498 exited0: **415 PASS in45.77s**, using the immutable
46-file final source closure. All source hashes matched before and after.
This is scripted FFT-port/control evidence with unchanged arithmetic and
mailboxes, **not actual vendor FFT, mapped timing, continuous receiver, IIO,
native-fine accuracy or deployment qualification**.

Tested source: FW`464e9bf34309501dd37089521288b81ccdbe5b4d`,
HDL`2e8a7de221889084ea58cc6c44dd9a8407c56c9f` in the separate high-rate60-paired
DNM lane. Final owner is the independently reviewed`b6280f6a` fence. All old
runtime files remain untouched; opt-in defaults off.

## Independent coverage review and results

Parent read the complete final test suite, helper/bench deltas from frozen17,
new clock/watchdog benches, graph/state helper and full implementation report.
The source differences outside test tooling are confined to the small owner
release fence already checked independently against valid/invalid ACK cases.
No numerical fixture, watchdog limit or source-clock constraint was relaxed.

- Nine healthy compositions each check1536 source/forward/product/inverse/read
  words and all expected metadata/positions/exponents. The next forward can
  overlap an old retained reader; next inverse requires registered real release.
- Both unchanged180-bit guards are shadowed unconditionally on their actual
  inputs. Separate original guard stimulus retains23 healthy/37 rejected/12
  reset cases; parent log records219315 comparisons. Default-disabled wrapper
  comparisons check1536 read words under each of two profiles.
- Every distinguishable cutover/raw-event case rejects with the original
  current/sticky protections. A frame1 offer exactly coincident with natural
  frame1 at offset13 is explicitly unobservable and must instead finish the
  full1536-word healthy replay; unknown injection is not OR-masked.
- Six full-overlap resets cover either raw reset, paused slow clock,512 unread
  old inverse words and active next-forward prefix. Fresh rejoin requires at
  least four actual slow edges and checks512 fresh third-fixture output words.
  Eight separate actual-mailbox paused-clock purge cases also pass.
- Three missing-output/status cases preserve the exact8192 active watchdog.
  A retained inactive reader can wait9899 clocks without inventing an active
  timeout. The stopped-reader case intentionally fails the25000-fast harness
  drain deadline while retaining ownership and reporting no protocol fault.

The parent's separate saved-result audit verifies XML415/no skip/error/failure,
all46 source pins, all403 compile/run receipts, nine schedule/ACK/clock records,
reset and watchdog inventories. Of the simulations,382 succeed and21 are
explicit expected failures:20 invalid entry configurations plus the stopped
reader. Expected failures have nonzero simulation exit and no OFFLINE_PASS.
Positive logs have PASS and no ERROR/FATAL line. No negative simulation is
silently relabeled as successful receiver operation.

## Schedule, resources and strict graph audit

First edges/half-periods now match the original accepted model at1fs precision:
fast half2857143fs, slow half5000000fs. Earlier17/415 rounded-clock snapshots
remain distinct evidence; they used2857000fs fast half-periods.

The independent log audit confirms8-clock next-forward dispatch when the next
source block is already full,3645-clock nominal/13-of17 publication recurrence,
and4911–4912 with the reader parked. An actual447/15MS/s source may be the
limiting arrival: these eager-source dispatch values are not a universal
end-to-end deadline. The9000-clock initial park is protocol-only:11711-clock
publication interval,9899 maximum real-ACK wait and capacity_claim0. No lower
clock was simulated or physically qualified.

Declared variable bits are2480 versus2257 in the baseline (+223): another
180-bit guard,17-bit owner,17-bit cutover and9-bit epoch barrier. Three512×36
payload arrays remain; no FFT/DSP is added. This is not mapped resource use.

The frozen helper's graph scope is limited: it checks L/LS reference closure,
but not all variable definitions/types or operation/function types. Parent wrote
a separate stricter audit on its fresh netlist: all referenced v/L/LS definitions
must exist; only declared variables/arrays are cuts; operations are allowlisted;
the one automatic boundary-rounding function is explicitly identified and read
in the pinned arithmetic source. Seven controls cover missing variable/LS,
unknown operation/cut/function, LS cycle, and genuine state cut. **5893 nodes,
69 LS nodes, no cycle.** This remains continuous connectivity, not Boolean
reachability, synthesis or physical timing.

Parent's first strict-audit attempt stopped before traversal because the path
glob also selected pytest's current symlink. The first script/result are retained;
excluding symlinked case directories was the only correction. No graph/parser
rule or RTL changed to obtain the result.

## Evidence and next step

Recovery:`retained415-parent.NuSfm0Ii` and
`retained-output-prototype-final-v1` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Source manifest SHA`a4dfa8d603d1d7782b51106c6224a3dc6dfbc67d07e241abac8d7c390f83aeb8`.
Parent XML`b1eabe050fac71029c9afa32a2e24450847f99aac49f1a21ae608664dbe2cb31`;
audit JSON`d4d1e261523ed755c89f2170aca1cd32ad9f85510347967e8f4920d54f67b3c9`;
strict graph JSON`800f900acab49f485812f9392a29671680e9ce39771c86a355907f939ab6cb43`.
Netlist`d4cc49489fe5bae5a6722fa463c7f26ae969a4dc3c5eb61630bf3d9ee3a56947`.

Archive`20260910-retained415-parent.tgz`:18985635 bytes,
SHA`81f3221bf6105d661869474f50016ece98a25716dc106ce508d72f03cbb7a2d6`;
tar comparison exited0. Includes all46 frozen source files, every parent compiled
VVP/expanded bench/log/exit, XML and independent audits. Only convenience symlinks
ending current are excluded; no parent compiled executable is inventory-only.

Source-frozen **actual FFT recipe/bundle preparation only** is now authorized;
execution still needs review. Preserve accepted original clocks/vectors/limits,
full arithmetic/guard evidence and separate bounded-reader versus long-reader
protocol profiles. No blanket CSV shift, lower-clock promotion or radio action.
In parallel the sealed-product approach needs two additional integration seams
(sampled READY and publication-only faults) before real P1 wiring. Firmware
branches remain DNM. Full receiver timing/calibration, canonical15 coarse/native
fine, independent2.5MS/s IIO,120ms/300s scanner and `.18` then Ethernet-only `.17`
deployment remain required; the last physical route still fails timing.
