# C1 physical preparation — offline only

The source-specific C1 preparation passed29 offline tests (original70166,
terminal0,30.51s). Root independently repeated29PASS31.12s. No synthesis,
placement, route, clock relaxation, timing waiver, or runtime edit occurred.

Tested source FW `093f245fd5553a303c11eca05ed187db455a5543`, HDL
`12cfcf67a12bbfaa58ee8026a36d1c82ee91b2e1`.
Prepared directory:
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-physical-prepared-v1`.
Its18-file inventory SHA is
`66001eba6a4bd5773f73ea1eaac9b730cd11e620900bbce072b1b0c5d0accb65`.
Preparation55287 exited0; no synthesis output directory exists.

The generator derives the physical helper through literal replacements; its
full inverse restores the entire reviewed `0fee7f69…` helper. The generated
Tcl likewise restores the previous R/D/S adapter in full after removing the
specific C additions. It admits only the exact successful C1 actual inventory
`9c81c43d…`, independently reruns its frozen original/qualified/CDC receipts,
requires original process exit0, verifies wrapper `e8285f5e…`, and keeps both
historical main and extra CSV hashes. C0/old111, failed/missing/wrong CDC
receipts, incomplete source audits, and nonzero process/time results fail.

R/D/S/C are explicitly1 in preparation metadata, generated Tcl bindings,
synthesis generics, readback, and scope receipts. Omitted, zero, duplicate,
conflicting, case-changed, or dropped C readback fails. No clock, source part,
IP factory, source closure, timing constraint, synthesis/route directive or
thread count changed. All seven runtime files come from the passing C1 run.

The exact generated helper SHA is
`c3e4d4ebc46928bb15b9134e3c4e056803cbec34f3389c8e7c22001669cde45a`;
generated synthesis adapter
`b36ba468bc1b8caa32ad1881bb021bf41098853ecea6921113569e63d7ab50d2`.
External owner remains byte-identical
`d0f36ce2817ab20baaff8668b6743e367d296f7a60e714099fe69aa5b6912111`;
route script remains
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
The owner preserves before/after audits even on physical failure, distinguishes
tool exit from verified completion, requires all eight nonempty products and
zero black boxes, and never retries or routes. Its existing tests were not
rerun solely for this preparation; the full owner bytes are unchanged.

Executed offline scope: whole helper/Tcl/owner inverses, both source closures,
generic/readback mutations, source/receipt rejection, no-overwrite/symlink
checks, and poisoned Python environment. Tcl traps stop before project
creation; each Python child is sanitized without changing its parent's
environment. No vendor tool was executed by these tests. Ruff passed.

Archive `hdl/library/starlink_pss_acquisition/evidence/fault-cdc-physical-offline-v1`
has50 members, inventory
`1f84d92f0e757b490acbb312da1e15ad904f053cb4f31f33e78d3c0869ff44f0`.
Git-object verification passed at HDL
`7c2e4f005dac450941830b7850dd9e20adc4dcf3`:50 members/51 tracked files.
Raw receipt is `/tmp/starlink-completed-input.5EaJuD/fault-cdc-physical-offline-git-audit-v1.log`.
contains the full prepared package, source/reference helpers, test source,
terminal log, staging logs, and compact Tcl/rejection receipts. Large copied
historical-log mutation fixtures remain local and are reproducible from the
immutable C1 actual archive plus literal test mutations; no original artifact
was removed. Prior111 synthesis/route and open CDC-10 evidence remain intact.

## Proposed single synthesis — separate authorization required

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  /tmp/starlink-completed-input.5EaJuD/fault-cdc-physical-prepared-v1/run_exact_control_synthesis.py \
  --execute-synthesis \
  --prepared /tmp/starlink-completed-input.5EaJuD/fault-cdc-physical-prepared-v1 \
  --expected 66001eba6a4bd5773f73ea1eaac9b730cd11e620900bbce072b1b0c5d0accb65 \
  --new-run /tmp/starlink-completed-input.5EaJuD/fault-cdc-synth-v1
```

The unchanged owner supplies Vivado2022.2's reviewed SuSE environment and
unique logs/journal before Tcl arguments. This must be one original owned
process, no timeout restart. Route is a separate decision after exact C1
source/DCP/clock/resource/CDC and completion review. Preparation itself does
not establish synthesis support, CDC closure, timing closure or releaseability.
