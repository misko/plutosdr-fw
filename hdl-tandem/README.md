# Tandem AGC v2 RTL

The historical canary first bounded whether a block of this size could fit a
Zynq-7010 that was already near 74% LUT. The production implementation now
uses the complete TAG2 AXI control surface described below; the canary source
is no longer part of the tree.

## Historical canary synthesis (superseded)

| Resource | Canary | Device | % | Plan §6 estimate |
|---|---:|---:|---:|---|
| LUT | 431 | 17,600 | 2.45% | 500–1,000 |
| FF | 502 | 35,200 | 1.43% | 600–1,400 |
| BRAM36 | 2 | 60 | 3.33% | ~1 |
| DSP | 0 | 80 | 0% | 0 |

WNS **+10.628 ns** against a 16.276 ns period, 0 failing endpoints of 792.
WPWS +7.638 ns.

These canary figures predate the current TAG2 AXI control surface and are not
release evidence for the current RTL.

## Historical canary caveats

Out-of-context, so no placement pressure and no routing congestion. The
integrated place-and-route against the RC17 baseline is the real answer.
The canary also omits the AXI4-Lite slave (a standard component, roughly
100–200 LUT and 150 FF) and simplifies the policy truth table.


---

## Implementation

`tandem_agc_core.v` is the receive-clock controller and `tandem_agc_axi.v` is
the only control surface. It implements the forward-only `TAG2` register ABI
with a coherent 59-bit, two-slot BRAM return mailbox containing the transition
watermark and low 32-bit exclusive sample fence alongside the other software-
observable state. Crossed reset-readiness levels keep both sides inactive until
even a stopped peer has clocked its local reset. Epoch configuration is already
AXI-local; retired-epoch and policy diagnostic counters remain core-local for
simulation and do not consume a second pair of wide CDC register banks.
used by the Linux ownership driver; the v1 standalone register wrapper has
been removed so it cannot become a second control path.
`ad9361_gain_model.v` is a behavioural model of the part; every behaviour in it
is either cited to UG-570 or measured by experiment E-AGC1.

## Routed out-of-context release gate

The reproducible block-level gate uses the complete `tandem_agc_axi` top with
its default event FIFO, both declared asynchronous clocks, placement, routing,
timing, DRC, methodology, and CDC reports. Run it only from a clean committed
tree and give it an absent output path:

    scripts/run_tandem_agc_ooc.sh /absolute/path/to/fresh-ooc-evidence

The launcher records the exact commit, tool version, input hashes, routed
checkpoint, and reports in that private directory. A strict, bounded offline
validator accepts only the frozen topology and rule inventory: CDC directions
112/39 with CDC-3=5, CDC-6=2, and CDC-15=133; OOC-only DRC
REQP-1839=18 and ZPS7-1=1; methodology TIMING-18=182 and LUTAR-1=1; exact clock
and resource capacities; complete route accounting; nonnegative timing slack;
zero timing failures; and no unknown rule. Volatile endpoint, routed-net, and
used-resource counts are parsed and cross-checked instead of being copied from
an older candidate. The complete directory contains the input snapshot and
hashes, Vivado and Python versions, provenance, log, routed checkpoint, eight
reports, normalized timing metrics, an evidence checksum manifest, and
`status.txt`.

`status.txt` is linked with no-replace semantics only after every report,
inventory, source, tool, and checksum check succeeds; its absence makes an
interrupted or rejected directory nonauthorizing. Its PASS is explicitly
block-level and `firmware_release_eligible=false`. Passing this gate is
necessary but does not replace the exact-commit integrated Pluto
implementation and routed timing/CDC checks used for a firmware candidate.

## Tests

    ./run_tests.sh

Six runs across five suites, all under Icarus Verilog:

| Suite | Covers |
|---|---|
| `tb_tandem_cdc` | reset bridges, coherent bus crossings, FIFO ordering, and explicit overflow |
| `tb_ad9361_model` | 27 checks that the model itself is faithful, including that a 1-ClkRF pulse is rejected and a 2-cycle one accepted |
| `tb_tandem_agc` (ratio 1.0) | closed loop at `rx_fir_dec = 2`, SPF production, including stale small-ADC-latch recovery and fail-closed persistent/high-PAPR conflict handling |
| `tb_tandem_agc` (ratio 2.0) | the same policy and latch-recovery checks at `rx_fir_dec = 1`, the device-tree boot default |
| `tb_tandem_agc_stress` | §8.2 edge cases: randomised traffic, reset in every lifecycle state, disable at every pulse phase, chatter, long idle, FIFO overflow, sequence and 64-bit counter rollover, zero-cooldown request/pulse and HOLD handoffs, index-mismatch fault |
| `tb_tandem_agc_axi` | exact `TAG2` ABI, 32-bit kernel epoch, 16-byte post-change events, asynchronous AXI/RX clocks, and HOLD-low teardown ordering |

The twelve §10 assertions run continuously as procedural checkers
(`tandem_agc_checkers.v`) — Icarus has no SVA and this repository uses none.

## Pre-recovery out-of-context reference (superseded)

The figures below predate the stale-small-ADC recovery state and are retained
only as the last size baseline. They are not timing/utilization evidence for the
current RTL. A new release candidate requires fresh out-of-context and
integrated synthesis evidence before any fit or timing claim is made.

| Resource | Core + regs | Device | % | Plan §6 estimate |
|---|---:|---:|---:|---|
| LUT | 516 | 17,600 | 2.93% | 500–1,000 |
| FF | 478 | 35,200 | 1.36% | 600–1,400 |
| BRAM36 | 2 | 60 | 3.33% | ~1 |
| DSP | 0 | 80 | 0% | 0 |

Against the measured RC17 baseline of 13,088 LUT, that prior core projected to
**13,604 LUT = 77.3%**, inside the ~82% guardrail, with DSP unchanged at 72/80.

The obsolete standalone wrapper and FIFO-only Tcl entry points have been
removed; neither represented the complete production control surface.

The checked-in integration patch and the pinned Pluto HDL source both retain
`EVENTS=1` and connect `rx_fir_decimator/valid_out_0` to `sample_valid`. Those
connections are release invariants: removing either one destroys the
sample-clock-aligned authoritative event timeline.
