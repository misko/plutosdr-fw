# Paused source clock: reproduced inherited reset boundary

This is a small real-RTL mailbox diagnostic, not a receiver simulation, hardware
failure report or a fix. It instantiates the unchanged L1 source mailbox with
`RESET_RELEASE_EXTERNAL=1` and reproduces the outer top's four reset-release
synchronizers. The output consumer is deliberately stalled throughout.

The source mailbox is pinned at HDL commit
`2c2460ad55981ed0833eeadfef60463f1d1bca10`, path
`library/starlink_pss_acquisition/starlink_pss_block_mailbox.v`, SHA-256
`e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55`.
The copied outer equations come from the unchanged
`starlink_pss_fft_bank_owned_local_admission_probe.v` reset block.

## Executed sequence and observation

1. At 100/175 MHz, fill one 512-word source bank; leave all output words unread.
2. Pause the slow clock low with the producer request toggle still 1.
3. Assert either raw reset and run five fast clocks. The fast reader is purged,
   but the slow producer's synchronously reset request has not seen a clock.
4. Release that reset while the slow clock remains paused. After 12 fast clocks,
   fast reset qualification is complete, slow qualification is not, and the fast
   reader has prefetched the old first word again.
5. Resume the slow clock without any new input writes. The producer eventually
   clears its request to 0, but the fast reader retains VALID with old word
   `0x123450000` at position 0.

Both reset-side runs reproduced this exact behavior. Icarus compilation and both
vvp commands exited 0 because the diagnostic intentionally asserts that the
counterexample occurs. Their marker explicitly says
`BASELINE_STALE_HEAD_REPRODUCED_NOT_A_SAFETY_PASS`; it must not be counted as
successful reset qualification. No radio, vendor core, firmware or PPU was used.

The bench and both original logs are in
[the diagnostic directory](20260910-paused-source-reset).
Original working artifacts remain at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/paused-source-reset-parent.eLviCa`.
Bench SHA-256:
`e21a572e40fe97bf33233efc4c0a9b45f548d4965924aece0376acbcf5f62c07`.

Reproduction with that exact mailbox source:

```sh
iverilog -g2012 -s tb_paused_source_reset -o simv \
  tb_paused_source_reset.sv /ABS/PINNED/starlink_pss_block_mailbox.v
vvp simv +SIDE=0
vvp simv +SIDE=1
```

## Consequence for the new inverse integration

Blocking scheduler admission alone does not erase a stale source-reader prefetch.
The default-off integration needs a reader reset barrier until a newly witnessed
slow-domain purge acknowledgement permits epoch rearm. Its source-fault
synchronizer must likewise not turn an unpurged old slow sticky cause into a new
fast-epoch fault. The original default path remains unchanged for comparison.

That barrier must not deadlock a legitimate *new-epoch* full forward source:
inverse producer/certificate idle describes inverse-return references, not
`!source_valid`. Park before WAIT_BANK enters preflight while waiting for rearm,
so a paused clock cannot consume the unrelated 63-cycle preflight deadline.
The next implementation must demonstrate this sequence is rejected/purged and
that fresh data still passes after rearm; those fix results are not established
by this reproducer.

## Independent barrier prototype: four passes, two rejected controls

A separate small bench, `tb_source_purge_barrier.sv`, adds a slow-domain purge
acknowledgement and a two-stage fast synchronizer. The acknowledgement can become
high only after the slow reset-release has been sampled on an actual slow edge;
the preceding edge has executed the source producer's synchronous purge. The
fast reader remains reset until that fresh acknowledgement arrives.

Four original runs passed all 512 fresh data words, positions, TLAST and metadata:
both raw reset sides, with either ordinary fresh filling after clock recovery or
an entire new source bank filled while the fast clock remains paused. The latter
checks that a legitimate full current-epoch source does not deadlock rejoining.
No pre-reset source word was accepted. Both controls compiled with `BARRIER=0`
failed with vvp exit 1 at exactly `stale source reader reopened before remote
purge`; the shell asserted that expected nonzero status.

Prototype SHA-256:
`790f2f3a3b1a98169b3c5884f697af16ef4248afe4b5799d16426ef609428d7f`.
Bench and all six raw logs are preserved beside the original reproducer.
Original execution directory remains
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/source-purge-barrier-parent.eeeBRw`.

```sh
iverilog -g2012 -s tb_source_purge_barrier -o simv \
  tb_source_purge_barrier.sv /ABS/PINNED/starlink_pss_block_mailbox.v
vvp simv +SIDE=0 +FILL_BEFORE_FAST=0
vvp simv +SIDE=1 +FILL_BEFORE_FAST=0
vvp simv +SIDE=0 +FILL_BEFORE_FAST=1
vvp simv +SIDE=1 +FILL_BEFORE_FAST=1
iverilog -g2012 -s tb_source_purge_barrier \
  -Ptb_source_purge_barrier.BARRIER=0 -o no-barrier-simv \
  tb_source_purge_barrier.sv /ABS/PINNED/starlink_pss_block_mailbox.v
# Each command below must fail at the stale-reader assertion.
vvp no-barrier-simv +SIDE=0 +FILL_BEFORE_FAST=0
vvp no-barrier-simv +SIDE=1 +FILL_BEFORE_FAST=0
```

This verifies the barrier idea only with the unchanged mailbox. It is not the
new inverse-bank RTL, does not exercise the source-fault synchronizer barrier,
and does not qualify the full scheduler, CDC constraints or hardware reset.
The actual opt-in composition must repeat these scenarios with its own signals.
