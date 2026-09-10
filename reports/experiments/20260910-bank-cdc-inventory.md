# Complete coarse bank CDC inventory — read-only, not signoff

The saved complete-coarse synthesis checkpoint contains all expected ownership,
fault and held-metadata paths. A new read-only audit enumerated each surviving
metadata destination, both stages of six ownership and two fault chains, four
common reset-release chains and the three actual payload RAM primitives. It
applied no clock, delay, exception or implementation command.

Executed with Vivado2022.2, exit0 at2026-09-10 02:40:36UTC. Audit source is
HDL `9fb83021`, SHA-256
`22b8e30e6d827a0f5ccee9fbbce0234b731ea35bb79db8f9cbfdb044d6932498`.
Its ten admission/preservation policy tests pass. They test the runner boundary,
not a substitute netlist or fabricated timing values.

The inspected DCP is the earlier complete-coarse synthesis, NOT the new
registered-control experiment or a full receiver:
`/tmp/starlink-coarse-alternatives.Y3JzOI/fft-island/hdl/library/starlink_pss_acquisition/build/bank-iq-synthesis-v1/iq_bank_owned_synth.dcp`,
SHA-256 `a474e29b2588013f230e81343761abc52b7fff46e7cf34fcf6e55cdf3f1b2ac4`.
The runner rejects an absent/mismatched hash, unsupported tool or existing output.
The checkpoint is opened and closed without writing it back.

## Measured structure

| Bank | Producer → consumer | Surviving held metadata, source / destination | Payload mapping |
| --- | --- | ---: | --- |
| Source |100 →175MHz|64 /64 of nominal70|one RAMB18, write B100/read A175|
| Product |175 →175MHz|69 /69 of nominal70|one RAMB18, both ports175|
| Output |175 →100MHz|75 /75 of nominal75|one RAMB18, write B175/read A100|

All208 surviving metadata destinations have individual timed paths from their
held source registers. Constant-optimized fields are reported as such, not
invented flops or silently treated as missing functional identity checks.
Each bank uses36-bit read A/write B, with opposite directions disabled. Source
and product DOA_REG/DOB_REG are0; output has both1. These are synthesized mappings,
not routed collision, interface or timing qualification.

Six ownership request/acknowledgement chains are present. Four cross clocks;
the product bank's two chains stay wholly in the fast clock domain. Two further
sticky fault chains cross source100→fast175 and fast175→source100. Both stages
of every chain retain ASYNC_REG. The four common reset-release chain pairs are
also present and marked, with their second-stage paths timed locally.

The actual saved clocks are separate primary port clocks:10.000ns and5.714ns,
not an integrated MMCM-derived clock relationship. Some cross-clock launch to
first-stage paths have a saved requirement of0.002ns; others1.145ns. Local
second-stage requirements remain5.714ns or10ns. The audit reports those values
unchanged, including negative slack. They are not relabelled as synchronizer
failure or successful timing closure. The real generated-clock integration
must establish its actual relationship and reviewed endpoint constraints.

There are no valid saved timing exceptions. CDC reports six synchronized1-bit
crossings, one synchronized asynchronous reset and139 clock-enable-controlled
metadata warnings:64 source-bank plus75 output-bank destinations. The139
warnings still require an ownership/stability/bus-timing argument; recognizing
the mailbox pattern does not dismiss them. Check-timing also retains103 input
and101 output ports without delays, and both OOC clock ports lack HD.CLK_SRC.

## Concrete integration requirements

1. Preserve FCLK1/200MHz for the AD9361 delay reference. Connect the tested
   dedicated100→175 MMCM only to the candidate FFT island, with explicit
   LOCKED/reset lifecycle. The active-traffic clock study is separate.
2. Add an explicit bank-profile structural gate, not a broader regex that makes
   the existing shared-service gate accidentally pass. The current gate expects
   `transform_service/input_mailbox` and `output_mailbox`, not these three banks.
3. Audit request and ACK direction independently; constrain only reviewed
   cross-clock endpoint paths. Keep second synchronizer stages and all product
   bank paths as ordinary same-clock setup/hold checks. Do not apply blanket
   asynchronous clock groups or exemptions to the complete island.
4. For bundled metadata, prove stability from first-word capture through the
   synchronized terminal-read ACK, then check every surviving destination and
   relevant bus-delay/skew bound. Preserve full logical metadata validation and
   actual final-read ownership; no truncated identity or partial-map reuse.
5. Qualify dual-port RAM ownership and epoch purge alongside reset release,
   clock loss/return visibility and current fault vetoes. Retain complete
   normalization, native fine, pilot DMA/IIO and real board-I/O checks in the
   eventual whole receiver. An isolated passing inventory cannot authorize flash.

No constraint or receiver-profile change was made by this audit. It narrows the
required integration work but does not fix the still-failing active input-check
timing path in the separate registered scheduling experiment.

## Retained evidence

`20260910-bank-cdc-inventory.tgz` contains the audit source, full runner log,
endpoint inventory, clocks, CDC, exceptions, ignored exceptions, timing and
check-timing reports. It excludes the DCP and generated vendor IP.
SHA-256: `715b2416f296a320daaa1d774ebc448e96f97972f05ca9439dc7f71666564541`.

Replay `audit_bank_owned_cdc_checkpoint.tcl CHECKPOINT EXPECTED_SHA256 NEW_OUTPUT`
with Vivado2022.2. A terminal `BANK_CDC_INVENTORY_WRITTEN` means only that the
diagnostic inventory completed; physical and receiver qualification stay false.
