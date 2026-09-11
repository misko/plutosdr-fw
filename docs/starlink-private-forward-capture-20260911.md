# Private forward capture progress — DO NOT MERGE

Only the new forward-return bank changes at runtime. Its write counter and
first-word exponent now follow the already-private RAM write independently of
the current descriptor/fault tree. A newly rejected beat can update these
private fields; fault_q and state quarantine on the same edge, while the
unchanged combinational fault still suppresses replay immediately. Invalid
payload/exponent values are not evidence and need not equal the parent when
output_valid is false. Common reset is required before reuse.

There is no added latency, capacity, arithmetic, timing exception or clock
change. The actual observer fragment, original bench and all 22 original
receiver runtime modules are unchanged. Parent bank source is retained in
/dev/shm/starlink-forward-return.FEyGL1Bw/prepared-v2.

## Tests and source-matched actual FFT

1115 distinct tests pass: 1099 regression plus 16 new guard/bank contract tests.
The 53 component/equivalence checks are included in the regression. An exact
inverse reconstructs the parent bank. Side-by-side parent/candidate execution
over 21 existing healthy/fault campaigns makes 85038 before/after-edge
comparisons. Controls, fault fencing and valid replay match; 72 observations
of changed private values are confined behind quarantine. This is finite
scenario coverage, not exhaustive formal equivalence.

Both source-matched actual-FFT observer campaigns pass with identical counts
to the parent: main 71 complete blocks / 37689 words; auxiliary 73 / 37455.
The totals include private prefixes later cancelled by fault tests. All 64512
original numerical records and original service 3663/3663/4929/11729/3663/3663
remain exact. Main/aux elapsed 209.61/186.89 s; regression 118.59 s. The observer
does not drive the original DUT. Buffered receiver scheduling is not tested by
these unchanged-service numbers.

## Standalone internal timing gate passes

Same standalone Vivado 2022.2 / xc7z010clg400-1 / 5.714 ns recipe:

| Metric | Parent | Private capture |
| --- | ---: | ---: |
| WNS (ns) | -0.181 | +0.186 |
| TNS (ns) | -7.073 | 0 |
| Setup failures / endpoints | 59 / 167 | 0 / 167 |
| Hold slack (ns) | +0.167 | +0.195 |
| Pulse slack (ns) | +2.357 | +2.357 |
| LUT / FF / RAMB18 / DSP | 75 / 111 / 1 / 0 | 72 / 111 / 1 / 0 |

151/151 nets route, zero errors. Matched replica-inclusive queries find all
70 descriptor and ten write-counter registers in both DCPs: the parent path
to write-count CE is -0.181 ns, while the candidate has no combinational path
from those descriptor registers to the write-counter data/enable/reset pins.
The new worst internal path is write-count bit 3 to state-machine enable,
seven levels (one CARRY4), 5.239 ns data delay. Capture capacity and the full
SDP writer enable/address controls remain independent of downstream READY.

197 input and 127 output ports remain unqualified by this isolated recipe.
This is a standalone internal timing pass, NOT integrated FFT/receiver timing,
CDC or physical signoff. The current receiver's known failing route is unchanged.

## Guard/bank integration contract

The actual guard RTL and actual bank RTL are connected in a new component
fixture. Raw FFT events and product-bank ownership are fixture-driven, not
generated FFT/product arithmetic. Both unrestricted guard mode and the known
completed-input/forward-retirement mode are exercised. Six positive scenarios
per mode cover ordinary completion, delayed status, delayed final fence,
delayed product ACK, final-edge abort/recovery and reset with held replay.
Two unsafe wiring mutations are rejected in both modes.

Critical sequencing rule: after raw word 511 the bank's capture_ready falls,
but the guard still holds its final result pending independent qualification.
The guard's final handshake must therefore use exclusive bank ownership, NOT
raw capture capacity. Otherwise final commit and seal deadlock. After commit,
READY must wait for actual qualified product ownership, not merely buffer
drain; a held commit pulse covers the transition into the persistent token.

The first fixture sampled combinational readiness in the same delta cycle as
deasserting raw_valid. Its six positive cases failed; adding a settling delay
to that bench assertion produced the required passes. No bank or guard RTL
was changed. Failed fixture sources/logs and both corrected runs are retained.
The first assessment counted pytest's latest-case symlink as a duplicate test;
the recorder now excludes that alias and counts 21 real runs.

## Next integration

Reserve the forward bank before core start, with an explicit admission/owner
receipt. Connect raw forward FFT output to local capture, guard qualification
to seal, and sealed replay to kernel/product processing. Keep the guard's
pre-commit ownership-ready separate from post-commit product ACK. Join all
current bank/input/vendor/status faults into the existing publication and
quarantine checks without introducing combinational fault feedback.

The old forward READY/retirement equivalence is specific to the old topology;
keep it as a reference test, not authority for new caller wiring. Re-prove
reservation, late final/status, bank/product completion, inverse admission,
reset/expiry and stale descriptor/epoch rejection with the actual FFT and
product buffers. Measure the complete service budget; the planning estimate
3663+512 versus 5215 clocks is not a proven sustained schedule. Then route the
integrated subsystem before adding features or promoting into the receiver.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain required.
Full receiver clocks/timing/CDC/reset, actual 60 MS/s calibration, sustained
Ethernet/IIO, blind GLRT comparison, 120 ms dwells and 300 s scans remain open.
Deployment requires pinned PPU/rollback on .18 first, then .17 over Ethernet.
No radios, PPU/main or primary HDL gitlink changed; .14/.20/.21 excluded.

Raw: /dev/shm/starlink-private-forward.hbi1EUk2.
Prepared SHA: 99af4fda00461dce42479a9d8ff6b053af08d0d5ada504877f2957d204b24114.
Bank SHA: 6fc9efc9c34a890e0b450bbd071417bf3e7ef933397ff4637d4eff8519173bbd.
Routed DCP SHA: eb3b18c3a00610a4985526bf2f9cb0a63dc3dfb02e90bfec6f60e90247e3c1e3.
