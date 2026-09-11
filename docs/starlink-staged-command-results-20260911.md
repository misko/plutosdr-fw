# Staged command controller: component timing PASS, integration outstanding

The new `starlink_pss_descriptor_commands` implements the two-stage ownership
contract from the preceding control review. It is separate from the older
same-cycle descriptor table and is not connected to the receiver yet.

## Interface contract

- One ready/valid command carries ALLOCATE=0, COMMIT=1 or RELEASE=2, a tag and
  optional full descriptor. Opcode 3 is invalid. Only accepted commands act.
- At accepting edge N, capture the command, selected slot and validation result.
  No ownership change is applied on that edge.
- At edge N+1, apply a valid command using the registered decision and assert
  its success response. Invalid validation quarantines the epoch instead.
- Hold response opcode/tag/valid until consumed. No new command is accepted
  while validation or a response is outstanding, so ownership cannot change
  between a tag check and its application. With response_ready high, command
  acceptance can occur every three clocks; this is not full FFT service time.
- Abort and unknown scalar protocol controls immediately fence authority and
  cancel pending work on the next edge. Invalid opcode/tag is reported after
  its validation edge, not combinationally from the incoming wide tag.
- Reset must drain/reset every external holder of old tags. No standalone
  cross-reset anti-alias guarantee is claimed. Tags never wrap within an epoch.
- Full allocation backpressures ALLOCATE. The upstream arbiter must prioritize
  releases and avoid placing an impossible allocation ahead of the release that
  could make room. An already asserted valid command must remain stable until
  accepted, except when the whole epoch is aborted/reset.

This is a descriptor ledger, not payload storage or an FFT completion validator.
COMMIT must follow validated payload completion and real buffer authority.
RELEASE must follow the actual consumer acknowledgement. Two descriptor entries
do not create a second output RAM or permit overwrite of a retained result.

## Functional verification

20 model-based tests pass, including exact response latency and backpressure,
abort/reset during validation or pending response, duplicate/stale/wrong-state
commands, generation exhaustion, every descriptor/tag bit and three 3000-cycle
ready/valid scoreboards. The combined extended suite passes 41 tests:
seven executed unsafe RTL mutants are rejected and fourteen X/Z interface
cases check staged validation versus immediate scalar abort behavior.

No runtime or primary model correction was needed after the first test run.
Physical execution used the source-frozen 20-test gate. The subsequent 21
negative tests use exactly that same RTL and model source.

## Registered-boundary physical result

Root session 10065 terminates successfully in 31.29 seconds. The independent
audit verifies the snapshot, copied RTL/Tcl, DCP, timing summary, twenty setup
paths, twenty hold paths, resource hierarchy and routing status.

- Clock period 5.714 ns, same xc7z010clg400-1 part; no timing exceptions added.
- **Setup WNS +0.765 ns**, TNS 0, zero setup failures across 874 endpoints.
- Hold +0.132 ns and pulse width +2.357 ns, zero failures.
- All 576 nets fully routed, zero routing errors.
- Controller: **182 LUT, 384 FF**, no DSP or RAM.
- Including probe boundary registers: 182 LUT, 638 FF; 254 FF belong to the probe.
- DCP SHA256:
  `c4c0028e268898545b8f5dafdfbc0c6a6b816aed0d564b7e836fe0463df569ed`.

Worst reported setup now runs from a stored tag through read-only lookup into
the probe's descriptor output register: five logic levels, 4.896 ns data delay
(1.776 ns logic, 3.120 ns route). It is not the earlier command-tag-to-allocation
enable chain. The controller costs 142 more FF and two more LUT than the first
same-cycle table; savings from replacing full-width metadata elsewhere have not
yet been demonstrated in an integrated receiver.

**Scope limitation:** this is component internal timing, not full island/receiver
closure. The probe's 141 inputs and 114 outputs have no board I/O delays, and its
physical clock-source location is unspecified. Real clock distribution, CDC,
reset recovery and placement in the full receiver remain qualification gates.

## Next integration gates

1. Connect the real scheduler and source/product/output bank owners through a
   command arbiter. Preserve actual ACK and publication authority; do not wire
   raw FFT status/TLAST directly into COMMIT.
2. Preserve complete timestamps in the descriptor store and carry job tags
   through the datapath. Bind visit/epoch/channel context to the job before
   removing redundant full-descriptor comparisons.
3. Prove no stale command/response survives retune, abort, reset or candidate
   expiry. Check input capture continuing while prior jobs compute or await readout.
4. Run actual vendor FFT numerical/frame verification, measure new service
   latency against the 15 MS/s coarse-block deadline and native fine-search budget.
5. Route the complete design and qualify real board clocks, RX calibration and
   sustained 60 MS/s plus independent 2.5 MS/s IIO.
6. `.18` reversible canary, then `.17` PPU Ethernet deployment and the 300-second,
   120 ms valid-dwell blind FPGA/host GLRT comparison. These gates remain open.

Evidence root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
`staged-commands-parent.gTQaWRvw` contains model/negative tests and generated
fixtures. `staged-commands-route-parent.jtHNJZ8K` contains the source-frozen
owner, physical run, reports, checkpoint and independent audit.
