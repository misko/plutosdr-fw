# GLRT ingress CDC and physical-boundary review

This is an engineering review of the task's own RTL and implemented reports.
No radio has been accessed. It does not approve deployment or establish a
measured ADC timing eye, metastability rate, transport headroom or live detection.

## Implemented evidence

HDL ff42d5ab passes full-board setup/hold and constrained Gray-bus skew at every
requested rate. Its report still identifies a two-input LUT driving FIFO reset
synchronizers (CDC-10/LUTAR-1), two reset-fanout patterns (CDC-11), and asynchronous
reset ancestry on BRAM control pins. The default DRC limits each RAM warning
class to 20 examples; those counts are not the total number of affected pins.

The independent prototype is in `artifacts/cdc-development-v1/hdl`.
Commit 1a0bafdc routes at 60 MS/s with setup/hold +0.094/+0.013 ns, 12879 LUTs,
13384 FFs, 4349/4400 slices, 72 DSPs and 46.5 BRAM tiles. Its Gray-bus actual
skews are 0.878/0.793/0.971 ns against a 2 ns bound. Full reports are in
`artifacts/board-60000000-cdc-v1/full-audit`.

That route removes CDC-10 and LUTAR-1. The remaining RAM examples have moved
out of the ingress FIFO to native template reads and FIR histories: asynchronous
FIFO readiness still feeds the receiver's fault/flush controls. Prototype
82173e4d adds two CPU-clocked, synchronously reset stages to that external health
signal. Its full 60 MS/s route passes at +0.029/+0.025 ns with no CDC-10,
LUTAR-1 or RAMB asynchronous-control warning. Its 2.5 MS/s build also passes
the normal build gate and is being audited. The main experimental HDL checkout
has advanced to 82173e4d. CDC-11 and inherited ADI handshake warnings remain
visible for the protocol review below; calibrated external I/O remains open.

## Reset and memory protocol

The FIFO receives the raw radio reset and CPU reset independently. Each input
asserts its own source-clock and CPU-clock reset synchronizers. No AND of two
independent readiness outputs drives an asynchronous clear pin.

The source-clock second stages also serve as separate acknowledgements. Each
acknowledgement crosses back through two CPU-clocked registers. The destination
keeps its read pointer, Gray-pointer synchronizers and output-valid pipeline
purged until both acknowledgements are observed. A reset asserted while the
ADC clock is stopped clears its source acknowledgement immediately; deasserting
that reset cannot restore the acknowledgement without actual ADC-clock edges.
The source pointer has therefore been synchronously reset before destination
release. Removing the old combined reset without this acknowledgement would
allow stale write pointers to become visible after a stopped-clock reset.

RAM write enable, address and payload are registered without asynchronous reset.
The reserved source pointer advances when a word is accepted; its published Gray
pointer advances on the following source edge, when that staged RAM write
commits. Publishing the reserved pointer immediately would allow a fast CPU
clock to read before a slow ADC clock committed the write. The full comparison
still uses the reserved pointer so the pending write consumes FIFO capacity.

The RAM read port reads every CPU edge from a synchronously reset pointer.
Output-valid logic, not an asynchronously changing RAM enable, discards reset
epoch data. RAM contents need not be erased: after the pointer purge, every
word published as available has first been written in the new epoch.

Prototype 82173e4d additionally delays the external health indication through
two CPU stages. Internal FIFO purge remains immediate. An active observation
losing source health or receiving the next gap-tagged word is faulted. Promised
IQ remains drainable, and the host rejects the observation's transport fault;
this change does not authorize stitching samples across a radio reset.

## Remaining reset fanout

CDC-11 identifies CPU reset reaching two source-clock chains: the free-running
counter release and the FIFO reset release. Their release edges need not agree.
The input-valid gate requires the counter/radio readiness levels, while the FIFO
independently requires its own reset release. A word occurring before both sides
are ready can only be discarded before the post-reset gap marker. Source health,
a seen nongap source word, and an unused clean visit are required before ARM.
An active radio reset invalidates the observation instead of creating a new
continuous coordinate span. These are reset protocol predicates; no data bus
is reconstructed by mixing bits from the two synchronizers.

This reasoning does not model analog metastability or minimum reset pulse width.
The reset fanout warnings remain visible in the report and are not suppressed
by changing their severity or by adding a blanket false path.

## Verification and limits

On ff42d5ab, 16 new tests queue old words, stop the ADC clock, assert/deassert CPU
or radio reset at four phases, then require clock acknowledgement before new
output. They distinguish counter rebasing on CPU reset from counter preservation
on radio reset. All pass. In the isolated 1a0bafdc prototype, 23 FIFO/ingress tests
and all 38 AXI/IQ/event tests pass, including 80 illegal-write/ingress phase
cases. In 82173e4d, the combined 61-test regression passes in 206.03 seconds.
Evidence is retained as `glrt-stopped-adc-reset-tests`, `glrt-cdc-ack-prototype-tests-v3`,
`glrt-cdc-ack-capture-tests-v1`, and `glrt-cdc-health-fence-tests-v1` XML files dated
20260909 under `artifacts/`.

All board variants still require runtime receive-interface qualification. The
inherited CMOS interface has 13 unconstrained RX data/frame inputs and two
ENSM-control outputs. Positive internal setup/hold does not close those paths.
The allocated canary run must retain actual rates, PN/data-eye results, calibrated
AD9361/FPGA delays, source-health counters, TX mute and restoration evidence.
Gray pointer maximum delay remains 7.5 ns and skew remains 2 ns; neither bound
was relaxed to obtain the routed results.

Finite native support is a separate outstanding ABI issue. The offline replay
now proves when a partial scorer is waiting for samples beyond the observation,
but the GLR1 hardware snapshot exposes only native/scorer busy bits. The host
event attestation therefore remains conservative and rejects a pending scorer.
The successfully exported IQ is preserved independently. Do not apply the
offline internal-state exception to hardware metadata without equivalent evidence.
