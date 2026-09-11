# Staged command controller: internal timing PASS

Implemented the registered command contract rather than extending same-cycle
fault/ownership logic. Command edge N captures tag validation and a slot decision;
edge N+1 applies that decision and produces a registered response. Ownership is
held stable until the response is consumed. Abort/reset cancels pending work;
invalid commands cannot produce success responses. Full descriptors remain
stored once, and tags cannot wrap within a coordinated epoch.

41 component tests pass: 20 transaction-model tests plus seven rejected unsafe
RTL mutants and fourteen four-state interface tests. The final combined suite
passes **231 tests in 37.19 seconds**. This includes the prior destination FFT
preparation/runtime/algebra and physical-policy tests, not a new integrated
receiver or RF run.

Root physical session 10065 terminates successfully in 31.29 seconds. Independent
audit verifies copied source hashes, DCP, internal setup/hold reports, timing
summary, hierarchy/resources, constraints and routing status:

- Setup **+0.765 ns**, TNS 0, zero failures across 874 endpoints.
- Hold **+0.132 ns**, pulse width +2.357 ns; zero failures.
- 576 nets fully routed, zero routing errors.
- Controller **182 LUT / 384 FF**, no DSP or RAM.
- Registered probe adds 254 FF, making 638 FF total.
- Same 5.714 ns clock and xc7z010clg400-1; no timing exceptions added.

The worst reported path is now read-only tag lookup into the probe's descriptor
output register: five logic levels and 4.896 ns data delay. It is not the earlier
wide command-validation-to-allocation-enable chain. Compared with the first
same-cycle table, the controller adds 142 FF and two LUT. Net savings in the
complete datapath remain to be measured after replacing repeated metadata.

**This is component internal timing, not full FPGA receiver closure.** The probe
still has 141 unconstrained input and 114 unconstrained output delays, with no
qualified physical clock-source location. Real board clocks, CDC/reset and full
receiver placement remain open. No radio or main branch was changed.

## Evidence and next steps

[Verified evidence package](20260911-staged-command-evidence.tgz): 1,309,661 bytes,
506 regular members, all checked against the embedded manifest. SHA256:
`5e999bdc8182fa7c60591e5f50b84a5a3606f268ec1716b02370fd0acd8119fb`.
Includes source snapshots, test fixtures, 231-test JUnit, reports and checkpoint.
DCP SHA256:
`c4c0028e268898545b8f5dafdfbc0c6a6b816aed0d564b7e836fe0463df569ed`.

Local evidence under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:
`staged-commands-parent.gTQaWRvw` and `staged-commands-route-parent.jtHNJZ8K`.

Next integrate a command arbiter with the actual FFT scheduler and payload-bank
owners. Allocation must not obstruct a required release; commit must use validated
completion and real payload authority, not raw FFT status. Preserve timestamps
and visit/epoch context while carrying compact tags internally. Prove retune,
expiry, abort/reset, backpressure and the new service deadline with actual FFT
numerics, then route the complete receiver. The remaining release gates are
sustained 60 MS/s native fine search plus independent 2.5 MS/s IIO, real RX
calibration, `.18` reversible canary, and `.17` PPU Ethernet deployment with the
300-second/120 ms valid-dwell blind FPGA/host GLRT comparison.
