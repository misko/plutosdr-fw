# Flat fault sources, original scalar register — DO NOT MERGE

The distributed capture experiment shortened the input path but moved an OR
tree after the fault registers. It regressed downstream timing and introduced
critical CDC-10 before the slow fault synchronizer. This candidate removes that
post-register reduction and restores the original single fast_fault register.

Only the previously checked nineteen-cause expression feeds its input. The
original synchronous reset, procedural true-only sticky capture, capture edge
and registered CDC source are retained. Current publication vetoes remain
unchanged. Known offered/contextual configuration uses the cause vector; other
or unknown configurations retain the original scalar fallback. No extra latency,
timing exceptions, clocks, arithmetic, sample-rate or interface changes.

Only the top changes relative to the distributed experiment. The actual-FFT
bench, all other runtime sources and synthesis helper/Tcl are byte-identical.
The scalar source inverse restores the distributed reference; the older
distributed inverse then restores its scalar parent. Historical behavioral
tests explicitly use the reconstructed distributed block, while separate tests
execute the current scalar block against the original scalar reference.

The current scalar block passes the same 313297 clocked four-state checks.
Reset, sticky persistence, individual/overlapping causes, context/fallback and
unknown values are covered; six defective mutations fail. Both actual FFT
campaigns must retain the source-vector/scalar and same-edge sticky witnesses,
all numerical/service checks, final handshakes, existing summary injections,
fault/reset cancellation and fresh recovery.

After matched routing, a dedicated structural gate requires a direct wire
from a scalar fast_fault register (or its physical replica) to the slow
synchronizer, ASYNC_REG on both stages, and isolated first-stage fanout. This
gate does not replace whole-design timing/CDC review. Compare targeted FFT-to-
fault capture and fault-register fanout with the rejected distributed checkpoint
and the earlier scalar reference. Do not promote on a local path improvement.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain required.
Full receiver timing/CDC/board clocks, actual 60 MS/s RX calibration, continuous
RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans remain
deployment gates. Then qualify pinned PPU/rollback on .18 before .17 over
Ethernet. No radios, PPU/main, primary HDL pointer or TX changes; .20/.21 excluded.

Raw evidence: /dev/shm/starlink-scalar-fault.xuB1HWdl.
Prepared SHA: b7a4a2bc1d143a8d30d0207261de5a73dfc989550c30d65082bfc63f8e57abeb.

## Measured outcome — not deployment eligible

1035 regression tests pass (117.43 s); the 18 component checks are a subset,
not additional distinct tests. Main/aux actual FFT pass in 209.37/192.48 s;
synthesis 102.50 s, route 51.81 s. All 64512 numerical rows and service clocks
3663/3663/4929/11729/3663/3663 are unchanged. Sticky witnesses cover
503565/437626 clocks; cause masks remain 0x663ff/0x40fdd. Actual campaign
coverage still does not assert cause groups 12, 15 and 16; those have finite
source-level checks, not integrated fault-injection coverage.

Direct scalar-register-to-synchronizer wiring and isolated first-stage fanout
pass. CDC inventory returns to nine CDC-3 and 208 CDC-15, with no critical
CDC-10. These remaining bundled-data warnings still need receiver-level review.

Global WNS -1.283 ns, TNS -255.361 ns, 607 setup failures; same-island WNS
-1.219 ns. Hold +0.058 ns and pulse +1.830 ns pass. 8478 nets route without
errors; 2759 LUT, 5795 FF, 21 DSP, 15 RAMB18. 114 inputs and 124 outputs are
unqualified by this isolated recipe. Routed DCP SHA:
6c4db93d45da7b3df0f24c79a401be9874f549586fa4330c08540479d6a67b64.

FFT-to-fault capture is -0.301 ns; fault-register-to-island worst -0.820 ns.
This recovers the distributed regression, but is NOT a general improvement
over the earlier scalar reference: that reference has 526 setup failures and
-1.189 ns same-domain WNS. The earlier READY-absorption candidate also remains
better overall (-1.245 ns / -245.991 ns / 453 failures). Do not promote solely
because the selected fault path improved.

The present same-domain worst starts at epoch_barrier/fast_release_reg and
ends at joiner/kernel_rom/output_valid_reg through product fault, framing,
commit and retirement qualification: nine logic levels, 6.930 ns data delay,
77.3% routing. A 2170-load derived release net is on this path. No path is
waived, and there is no timing-closure or native-RF-accuracy claim.

## Next structural experiment

Evaluate a block-owned forward FFT return buffer before modifying more shared
fault equations. Reserve it before starting the real-time FFT; capture the
complete 512-word return with local write control, then replay to kernel/product
processing through a separate registered read controller. Carry block metadata
once, check count/LAST/identity before sealing, and invalidate on fault/reset.
Keep current public publication vetoes; private capture is not publication.
This should remove downstream kernel/product readiness from FFT return capture,
but that is a hypothesis requiring mapped-path evidence, not an established cut.

First inventory existing storage and explore reuse versus one additional
512x36 payload bank (18432 bits, nominal one RAMB18 in suitable simple-dual-port
mode; actual inference/metadata must be measured). Budget a conservative extra
512 replay clocks against the present 3663 normal service clocks and the
5215-clock coarse-arrival interval. 4175 clocks is an estimate, not a proven
schedule; final hold, FFT reconfiguration, fault recovery and sustained arrivals
must be included. Do not lower the 60 MS/s or 2.5 MS/s inspection requirements.

Test the buffer/controller with stalls, exact-full limits, stale epochs,
malformed LAST/identity, reset/fault on final capture and replay, and unchanged
capture timestamps. Then integrate the actual FFT and retained buffers and
route that bounded subsystem. Reject if memory/service budget or whole-design
timing regresses; keep earlier source-pinned candidates as comparison points.
