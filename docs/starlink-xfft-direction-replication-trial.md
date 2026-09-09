# Targeted FFT direction-register replication: controlled trial proposal

Status: a guarded runner and policy tests are implemented. **One authorized
post-route attempt was rejected by Vivado before replication; no routing was
performed.** The exact option is not supported in post-route mode in 2022.2,
despite the general command documentation. The earlier help-based inference
that this particular option was usable post-route is therefore disproven.
The retained runner reproduces a negative experiment, not a working timing fix.
No FFT configuration/arithmetic, RTL latency, clocks, timing exceptions or radio
FW was changed. Any future post-placement trial needs separately reviewed
source/checkpoint admission; do not unroute this final DCP as a workaround.

## Measured source and exact target

Inspected Vivado 2022.2 final checkpoint for HDL `2e552234`:

`hdl/projects/pluto/shared-realtime-control-cut-v1/pluto.runs/impl_1/system_top_postroute_physopt.dcp`

SHA256: `e27f7524025c55b28aecc2f956293a7e6db1c666e6f19ad572575a43cb86ff1c`.
The hash was unchanged after both read-only inspections.

The exact source cell is:

```text
i_system_wrapper/system_i/starlink_pss_acquisition/inst/acquisition/shared_transform.iq_to_score/realtime_transform.transform_service/shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/single_channel.datapath/i_fwd_inv_reg
```

Inventory: one FDRE source, one Q pin/driver, one directly connected net,
one canonical top net, fourteen hierarchical segments, and 56 leaf load pins
on 56 leaf cells. The existing `*i_fwd_inv_reg*` name family contains only this
one cell; there are no existing replicas under that name family.

The direct net is the cell's sibling `single_channel.datapath/i_fwd_inv`.
The canonical top net is one hierarchy level higher:

```text
.../non_floating_point.arch_b.xfft_inst/i_fwd_inv
```

All fourteen names are segments of this **one** logical net, not fourteen
independent replication targets. Resolve the net from the verified source Q
pin and assert singular driver/top-net cardinality.

The source is at `SLICE_X33Y2/BFF`; 17 loads are at X11/Y61–65, 17 at
X22/Y58–62, 17 at X36/Y41–45, four at X6/X8/Y0, and one feedback LUT at X33/Y2.
Its worst reported vendor-internal path is −1.144 ns: 5.939 ns data delay,
including 4.358 ns routing on the direction net, followed by a LUT and four
carry cells. The input path into the source D pin has +3.218 ns worst slack
in the inspected report. That margin is **not** a guarantee that distant
replicas' D paths will meet timing.

Neither the source cell nor its net is location/routing-fixed; no DONT_TOUCH
value was found on the inspected source hierarchy. Two vendor parent levels
retain soft KEEP_HIERARCHY. Do not remove any hierarchy protection speculatively.

## Installed option and its experimentally established phase restriction

The installed primary reference is
`/opt/Xilinx/Vivado/2022.2/doc/eng/man/phys_opt_design` (lines 140 onward), also
confirmed by the actual binary's `phys_opt_design -help` output. It documents:

```tcl
# Attempted once below; Vivado 2022.2 rejects this in post-route mode.
phys_opt_design -force_replication_on_nets $verified_single_net_object -verbose
```

The argument must be a `get_nets` object. The help describes forcing the driver's
replication based on load placement, independent of its slack. The tool decides
the number of replicas; this option does not promise a particular count or
fanout. Specific optimization options disable unrelated default optimizations.
Do not combine the first trial with a broad directive, retiming, clock skew,
hold insertion, MAX_FANOUT edits, global fanout optimization or manual LOCs.
Do not use `-quiet`, which the installed help explicitly says can hide errors.

The actual binary returned `[Vivado_Tcl 4-265]`: this option is not supported
for post-route physical synthesis. General availability of `phys_opt_design`
post-route does not establish availability of every individual option there.
The experiment stopped at that rejection, without trying another mode/option.

The installed Tcl Store `replicate_high_fanout_registers` helper is primarily
a post-synthesis register-fanout utility; it is not the first choice for this
placement-driven, single-net experiment. No helper was sourced or
executed. No synthesis/IP regeneration is required for the proposed trial.

## Required semantic audit for any separately approved working experiment

1. Reopen the immutable baseline into a fresh, uniquely named trial directory.
   Retain its hash, source inventory, primitive configurations, all 56 original
   leaf consumer pins, fan-in connections, timing, route status, resource counts
   and constraint reports. A later-source checkpoint must be re-inventoried;
   do not silently reuse this checkpoint's counts or timing as its baseline.
2. Execute exactly one targeted replication pass. Inventory all changed/new
   cells and nets; do not infer success from an `_replica` name or exit code.
   A no-op, skipped target or unexpected logical changes is a failed/limited
   experiment, not a reason to broaden the selection automatically.
3. Require every replica to retain the original effective sequential function:
   same FDRE behavior, same active clock edge, same D function, CE/R sources and
   polarities, and the same effective initialization. Prefer the simplest check:
   original and replicas share canonical D/C/CE/R drivers. If the tool also
   clones the D LUT/feedback, require an explicit combinational equivalence
   check with all equivalent Q copies normalized; do not assume equivalence
   merely from a matching cell type or net name.
4. **Physical initialization matters.** In this routed checkpoint the logical
   INIT/inversion properties are present but unset, while the actual source
   BEL has `CONFIG.FFINIT=INIT1`, `CONFIG.FFSR=SRLOW`, `LATCH_OR_FF=FF` and
   `SYNC_ATTR=SYNC`. Blank INIT must not be replaced with a simulation-library
   default. Compare the effective BEL/site configuration and pin mapping,
   including mapped clock polarity, for original and replicas.
5. Source C is `sys_200m_clk`; CE is VCC; R is GND. D is the
   `i_fwd_inv_i_1` LUT output. That LUT receives `i_fwd_inv_tmp_reg/Q`, delayed
   load-start, and the original direction Q feedback. It is a real dynamic
   sequential state function, **not** a static net or a multicycle exception.
   Equal initialization plus equal transition functions establishes equal
   Q values inductively; this is the required argument for safe redistribution.
6. Every one of the 56 original leaf consumers must remain connected exactly
   once to an equivalent original/replica Q, with no lost/new consumer, extra
   data-path stage, altered arithmetic or unreviewed logical cone. Account for
   new D/C/CE/R loads separately. If the tool changes any additional logical
   structure, stop qualification pending a wider equivalence review.

## Physical success gate and limits (not reached by the rejected attempt)

After the semantic checks, retain the modified checkpoint in the new directory
and complete normal routing if the operation leaves any nets unrouted. Preserve
the baseline routing policy; any reroute or broader optimization is a separate,
clearly recorded step. The original DCP is never overwritten.

Measure both directions of the moved timing burden: all source/replica output
paths and all source/replica D/CE/R paths. Require ordinary 5 ns setup **and**
hold timing, legal placement, and complete routing. Also inspect full vendor
internal timing, guard/publication/BRAM controls, 100 MHz timing, sticky-fault
crossings, bus skew and all existing constraint checks. Keep 10 ns / 5 ns clock
periods and existing exceptions unchanged; compare constraint reports, including
the required sticky-fault crossing gates. Record LUT/FF/slice/control-set delta.

A better direction path does not close the receiver. No-op replication,
placement pressure, a newly critical D fanout, or worse unrelated timing are
valid negative outcomes. Do not claim a numerical or capacity requalification
from physical reports alone. Source arithmetic remains unchanged, while the
post-transformation semantic audit must still pass before trusting that fact.

## Implemented runner and negative result

New runner: `hdl/projects/pluto/trial_shared_realtime_direction_replication.tcl`.
New policy tests: `tests/test_starlink_direction_replication_policy.py`.
The six required arguments are `CHECKPOINT NEW_OUTPUT_DIRECTORY HDL_COMMIT
SHA256 MODE TRIAL_ID`. Both modes require Vivado 2022.2, a full immutable
source commit, an exact checkpoint hash, and a nonexistent output directory.
`inspect read-only-inspection` never enters the physical-operation branch.
`replicate` additionally pins the independently authorized source/hash and
`shared-realtime-0463-direction-replication-v1` identity. Source association is
explicitly caller-attested build provenance, not inferred from DCP contents.

The first real inspection exposed unsupported Tcl 8.6 `try` syntax before
checkpoint loading; that failed attempt is retained as `runner-inspect-v1`.
The corrected Tcl 8.5-compatible catch/options runner passed actual Vivado
inspection on the sealed `2e552234` / `e27f7524` checkpoint. Its baseline audit
resolved physical INIT1, pin mapping/polarities, source D/CE/R/clock connections,
feedback LUT function, 56 consumers and ordinary 5 ns timing requirements.

The sole authorized physical command was then attempted on:

```text
source: 0463f887d592452c940d3c70589becc330d70a0c
checkpoint: hdl/projects/pluto/shared-realtime-publication-cut-v1/pluto.runs/impl_1/system_top_postroute_physopt.dcp
SHA256: bc9060040b8577c780b4df1b8ecf482986a744563c510e1bd13150c1b01e7e3a
output: hdl/projects/pluto/shared-realtime-publication-cut-v1/direction-replication-v1
```

Exit 1, terminal 2026-09-09 08:45:47 UTC: the binary rejected the exact option
as unsupported post-route. `operation_started=1` records a command attempt,
**not a successful mutation**. `routing_performed=0`; the original checkpoint
hash is unchanged. The retained rejected checkpoint remains fully routed:
33,309 / 33,309 routable nets, zero routing errors. No replica equivalence,
post-replication timing improvement, numerical equivalence or receiver closure
is claimed. Actual post-transformation checks could not be exercised because
the command was rejected first.

The current tests pass 28 new cases; with the existing routed-audit policy
tests, 49 pass, and Ruff is clean. These exercise exact source/hash/mode/identity admission,
fresh-output protection, immutable source snapshots, retained negative receipts,
strict Tcl signature mutants (INIT, polarity, pin map, D driver), and rejection
of no-op/removed/type-changed/unrelated-new-cell footprints. They do not replace
an actual successful physical transformation and semantic audit.

| Artifact | SHA256 |
| --- | --- |
| Runner and frozen trial copy | `a6f9c630734b069978f164767a37513519bb180a6b7970c3bd13ebc0484a3d26` |
| New policy test | `b905a3481319e90acf9a6a3c412876f662b7b9848fb2ce1a40b7865ad58fa4c6` |
| Trial `summary.txt` | `5f67d62c026426d64753394f0492f4f6e161defed77f7f56be130b018b4a2438` |
| Trial `rejected_trial.dcp` | `77ee900f2513ca03630471928d7b96065d4e3637cf913896162613b6cf5a8526` |
| Trial `rejected_route.rpt` | `1de1795be952bb98d69bdb3b325601568eb11016c5710b1c880071c7e7b8222c` |
| Sibling `direction-replication-v1.log` | `aed25a6f2139cfaae0d7314ed3fcb3117dc6261843661dcc9272fbd1b7c72291` |

## Retained preliminary read-only evidence

Both inspection processes exited 0; neither called optimization, placement,
routing, property/constraint setters, checkpoint writes or hardware tools.

Directory: `/tmp/starlink-direction-readonly.rSWVfX/`

| Artifact | SHA256 |
| --- | --- |
| `inspect.tcl` | `344638fdd6ca6690ee4396f9b0fe674399441d6088eca09c83e07bc051d3ddad` |
| `inventory.log` | `a932027903454cd6b0d5ba24c6335eda49264828237f9c7bfc9689a861a89277` |
| `inspect_semantics.tcl` | `c4d264e3901543b42b580482c812c01e6ef0bf2ae1647619531748db754fb975` |
| `semantics.log` | `7dd8ee91ce00a9008e661aeb1a383d06808eeb32ebff10d872af995c66d46910` |
| Installed `phys_opt_design` manual | `cf477dd7a732ded07689d37411085d63ed5d7ec46324fd07480d39b91053c2d0` |

These temporary logs should be copied into any later controlled trial's
immutable evidence bundle before its report relies on them long-term.
